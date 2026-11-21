// Gestos pela câmera (webcam do notebook ou por cabo), reconhecidos NO NAVEGADOR com o
// MediaPipe. O vídeo nunca sai do computador: só a biblioteca e o modelo são baixados
// (uma vez) da internet. Ligado só quando você aperta ✋ Gestos.
//
// Gestos (nomes do modelo do MediaPipe):
//   Open_Palm  ✋  parar (fala e pedido)        Thumb_Up   👍  aprovar confirmação
//   Thumb_Down 👎  negar confirmação            Victory    ✌️  liga/desliga o ao vivo
//   Pointing_Up ☝️ fazer um pedido falado

const GESTOS_ROTULOS = {
  Open_Palm: "✋ parar", Thumb_Up: "👍 aprovar", Thumb_Down: "👎 negar",
  Victory: "✌️ ao vivo", Pointing_Up: "☝️ falar",
};

// Filtro puro (testável): um gesto só vale depois de ficar parado `estavelMs` com
// confiança >= `confianca`. Depois de valer, só vale de novo após `pausaMs` E a mão sair
// de verdade por `soltarMs` (a câmera perder a mão num quadro não repete o gesto).
function novoFiltroGestos({ estavelMs = 600, pausaMs = 1500, confianca = 0.7, soltarMs = 400 } = {}) {
  let atual = "", desde = 0, disparado = "", livreEm = 0, vazioDesde = null;
  return function (nome, pontuacao, agora) {
    const valido = nome && nome !== "None" && pontuacao >= confianca && GESTOS_ROTULOS[nome];
    const gesto = valido ? nome : "";
    if (!gesto) {
      if (vazioDesde === null) vazioDesde = agora;
      if (agora - vazioDesde >= soltarMs) disparado = "";
      atual = "";
      return null;
    }
    vazioDesde = null;
    if (gesto !== atual) { atual = gesto; desde = agora; if (gesto !== disparado) disparado = ""; }
    if (gesto === disparado || agora < livreEm) return null;
    if (agora - desde < estavelMs) return null;
    disparado = gesto; livreEm = agora + pausaMs;
    return gesto;
  };
}

const Gestos = (() => {
  const VERSAO = "0.10.14";
  const BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSAO}`;
  const MODELO = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/" +
    "gesture_recognizer/float16/1/gesture_recognizer.task";
  let reconhecedor = null, video = null, fluxo = null, ligado = false, ultimoQuadro = 0;
  let filtro = novoFiltroGestos(), aoGesto = () => {};

  async function carregar() {
    if (reconhecedor) return reconhecedor;
    const { FilesetResolver, GestureRecognizer } = await import(`${BASE}/vision_bundle.mjs`);
    const arquivos = await FilesetResolver.forVisionTasks(`${BASE}/wasm`);
    const opcoes = (delegate) => ({ baseOptions: { modelAssetPath: MODELO, delegate },
      runningMode: "VIDEO", numHands: 1 });
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
        const gesto = filtro(melhor ? melhor.categoryName : "", melhor ? melhor.score : 0, agora);
        if (gesto) aoGesto(gesto, GESTOS_ROTULOS[gesto]);
      } catch (e) { /* um quadro ruim não para o reconhecimento */ }
    }
    requestAnimationFrame(quadro);
  }

  async function ligar(callback, elementoVideo, idCamera) {
    if (ligado) return true;
    aoGesto = callback; video = elementoVideo; filtro = novoFiltroGestos();
    const imagem = idCamera ? { deviceId: { exact: idCamera } } : { width: 640, height: 480 };
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

if (typeof module !== "undefined") module.exports = { novoFiltroGestos, GESTOS_ROTULOS };
