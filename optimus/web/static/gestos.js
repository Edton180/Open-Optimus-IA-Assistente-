// Gestos pela câmera (webcam do notebook ou por cabo), reconhecidos NO NAVEGADOR com o
// MediaPipe. O vídeo nunca sai do computador: só a biblioteca e o modelo são baixados
// (uma vez) da internet. Ligado só quando você aperta ✋ Gestos.
//
// Gestos parados (nomes do modelo do MediaPipe):
//   Open_Palm  ✋  parar (fala e pedido)        Thumb_Up   👍  aprovar confirmação
//   Thumb_Down 👎  negar confirmação            Victory    ✌️  liga/desliga o ao vivo
//   Pointing_Up ☝️ fazer um pedido falado       Closed_Fist ✊ liga/desliga as respostas em voz
//   ILoveYou   🤟  alterna Núcleo (HUD) e Conversas
// Gestos em movimento (calculados aqui pela posição do pulso):
//   Swipe_Left / Swipe_Right 👈👉 tela anterior/próxima   Swipe_Up / Swipe_Down 👆👇 rolar

const GESTOS_ROTULOS = {
  Open_Palm: "✋ parar", Thumb_Up: "👍 aprovar", Thumb_Down: "👎 negar",
  Victory: "✌️ ao vivo", Pointing_Up: "☝️ falar", Closed_Fist: "✊ voz liga/desliga",
  ILoveYou: "🤟 trocar Núcleo/Conversas",
  Swipe_Left: "👈 tela anterior", Swipe_Right: "👉 próxima tela",
  Swipe_Up: "👆 rolar para baixo", Swipe_Down: "👇 rolar para cima",
};
const GESTOS_PARADOS = ["Open_Palm", "Thumb_Up", "Thumb_Down", "Victory", "Pointing_Up",
  "Closed_Fist", "ILoveYou"];

// Filtro puro (testável) dos gestos parados. Mais preciso que "N quadros seguidos": olha a
// janela dos últimos `estavelMs` e só vale quando o mesmo gesto aparece em pelo menos
// `maioria` dos quadros (um quadro errado no meio não zera a contagem), com confiança
// >= `confianca` e a mão quase parada (`maxMovimento`, fração da imagem) para não disparar
// enquanto você mexe a mão. Depois de valer, só vale de novo após `pausaMs` E a mão sair de
// verdade por `soltarMs`. `bloquear(ate)` segura tudo (usado depois de um deslize).
function novoFiltroGestos({ estavelMs = 600, pausaMs = 1500, confianca = 0.7, soltarMs = 400,
  maioria = 0.75, minQuadros = 4, maxMovimento = 0.12 } = {}) {
  let janela = [], disparado = "", livreEm = 0, vazioDesde = null, bloqueadoAte = 0;
  function filtro(nome, pontuacao, agora, pos) {
    const valido = nome && pontuacao >= confianca && GESTOS_PARADOS.includes(nome);
    const gesto = valido ? nome : "";
    if (agora < bloqueadoAte) { janela = []; return null; }  // depois do bloqueio, segure de novo
    janela.push({ t: agora, g: gesto, p: pos || null });
    while (janela.length && janela[0].t < agora - estavelMs) janela.shift();
    if (!gesto) {
      if (vazioDesde === null) vazioDesde = agora;
      if (agora - vazioDesde >= soltarMs) disparado = "";
      return null;
    }
    vazioDesde = null;
    if (agora < livreEm || gesto === disparado) return null;
    if (janela[0].t > agora - estavelMs || janela.length < minQuadros) return null;
    const iguais = janela.filter((q) => q.g === gesto);
    if (iguais.length / janela.length < maioria) return null;
    const pontos = iguais.map((q) => q.p).filter(Boolean);
    if (pontos.length > 1) {
      const xs = pontos.map((q) => q.x), ys = pontos.map((q) => q.y);
      const mov = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
      if (mov > maxMovimento) return null;
    }
    disparado = gesto; livreEm = agora + pausaMs;
    return gesto;
  }
  filtro.bloquear = (ate) => { bloqueadoAte = Math.max(bloqueadoAte, ate); janela = []; };
  filtro.progresso = (agora) => {
    // Para a dica na tela: qual gesto está sendo segurado e quanto falta (0..1).
    const ultimos = janela.filter((q) => q.g);
    if (!ultimos.length) return null;
    const g = ultimos[ultimos.length - 1].g;
    const desde = (ultimos.find((q) => q.g === g) || {}).t ?? agora;
    return { gesto: g, progresso: Math.min(1, (agora - desde) / estavelMs) };
  };
  return filtro;
}

// Detector puro (testável) de deslizes: o pulso anda `distancia` (fração da imagem) em até
// `janelaMs`, numa direção clara (o outro eixo anda menos da metade). A imagem da câmera é
// espelhada: pulso indo para a esquerda da imagem = sua mão indo para a SUA direita.
// A mão precisa estar à vista há `aquecerMs`: levantar a mão até a câmera não vira deslize.
function novoDetectorDeslize({ janelaMs = 500, distancia = 0.22, pausaMs = 900, aquecerMs = 300 } = {}) {
  let trilha = [], livreEm = 0, vistaDesde = null;
  return function (pos, agora) {
    if (!pos) { trilha = []; vistaDesde = null; return null; }
    if (vistaDesde === null) vistaDesde = agora;
    if (agora - vistaDesde < aquecerMs) return null;
    trilha.push({ t: agora, x: pos.x, y: pos.y });
    while (trilha.length && trilha[0].t < agora - janelaMs) trilha.shift();
    if (agora < livreEm || trilha.length < 3) return null;
    const dx = trilha[trilha.length - 1].x - trilha[0].x;
    const dy = trilha[trilha.length - 1].y - trilha[0].y;
    let gesto = null;
    if (Math.abs(dx) >= distancia && Math.abs(dy) < Math.abs(dx) / 2) gesto = dx < 0 ? "Swipe_Right" : "Swipe_Left";
    else if (Math.abs(dy) >= distancia && Math.abs(dx) < Math.abs(dy) / 2) gesto = dy < 0 ? "Swipe_Up" : "Swipe_Down";
    if (gesto) { livreEm = agora + pausaMs; trilha = []; }
    return gesto;
  };
}

const Gestos = (() => {
  const VERSAO = "0.10.14";
  const BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSAO}`;
  const MODELO = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/" +
    "gesture_recognizer/float16/1/gesture_recognizer.task";
  let reconhecedor = null, video = null, fluxo = null, ligado = false, ultimoQuadro = 0;
  let filtro = novoFiltroGestos(), deslize = novoDetectorDeslize(), aoGesto = () => {};
  let aoDetectar = () => {};

  async function carregar() {
    if (reconhecedor) return reconhecedor;
    const { FilesetResolver, GestureRecognizer } = await import(`${BASE}/vision_bundle.mjs`);
    const arquivos = await FilesetResolver.forVisionTasks(`${BASE}/wasm`);
    const opcoes = (delegate) => ({ baseOptions: { modelAssetPath: MODELO, delegate },
      runningMode: "VIDEO", numHands: 1, minHandDetectionConfidence: 0.6,
      minHandPresenceConfidence: 0.6, minTrackingConfidence: 0.6 });
    try { reconhecedor = await GestureRecognizer.createFromOptions(arquivos, opcoes("GPU")); }
    catch (e) { reconhecedor = await GestureRecognizer.createFromOptions(arquivos, opcoes("CPU")); }
    return reconhecedor;
  }

  function quadro() {
    if (!ligado) return;
    const agora = performance.now();
    // ~10 imagens por segundo bastam para gestos e poupam CPU em PC fraco.
    if (agora - ultimoQuadro >= 100 && video.readyState >= 2) {
      ultimoQuadro = agora;
      try {
        const r = reconhecedor.recognizeForVideo(video, agora);
        const melhor = r.gestures && r.gestures[0] && r.gestures[0][0];
        const mao = r.landmarks && r.landmarks[0];
        // Centro da palma (pulso + base dos dedos): mais estável que um ponto só.
        const pos = mao ? { x: (mao[0].x + mao[5].x + mao[17].x) / 3,
                            y: (mao[0].y + mao[5].y + mao[17].y) / 3 } : null;
        const passou = deslize(pos, agora);
        if (passou) {
          filtro.bloquear(agora + 1000);  // o fim do deslize não vira um ✋ sem querer
          aoGesto(passou, GESTOS_ROTULOS[passou]);
        } else {
          const gesto = filtro(melhor ? melhor.categoryName : "", melhor ? melhor.score : 0, agora, pos);
          if (gesto) aoGesto(gesto, GESTOS_ROTULOS[gesto]);
        }
        aoDetectar(filtro.progresso(agora), !!mao);
      } catch (e) { /* um quadro ruim não para o reconhecimento */ }
    }
    requestAnimationFrame(quadro);
  }

  async function ligar(callback, elementoVideo, idCamera, detectando) {
    if (ligado) return true;
    aoGesto = callback; video = elementoVideo; aoDetectar = detectando || (() => {});
    filtro = novoFiltroGestos(); deslize = novoDetectorDeslize();
    const tamanho = { width: { ideal: 640 }, height: { ideal: 480 } };
    const imagem = idCamera ? Object.assign({ deviceId: { exact: idCamera } }, tamanho) : tamanho;
    fluxo = await navigator.mediaDevices.getUserMedia({ video: imagem, audio: false });
    video.srcObject = fluxo; await video.play();
    try { await carregar(); }
    catch (e) { desligar(); throw new Error("não consegui baixar o reconhecedor de gestos (sem internet?)"); }
    ligado = true; requestAnimationFrame(quadro);
    return true;
  }

  function desligar() {
    ligado = false;
    if (fluxo) fluxo.getTracks().forEach((t) => t.stop());
    fluxo = null;
    if (video) video.srcObject = null;
  }

  async function cameras() {
    try { return (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput"); }
    catch (e) { return []; }
  }

  return { ligar, desligar, cameras, get ligado() { return ligado; } };
})();

if (typeof module !== "undefined") module.exports = { novoFiltroGestos, novoDetectorDeslize, GESTOS_ROTULOS };
