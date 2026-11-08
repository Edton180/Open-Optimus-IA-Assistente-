/* HUD do Optimus: orbe central com anéis segmentados, sequência de abertura, relógio e
   gráfico de CPU. Só canvas 2D, sem bibliotecas: roda leve até em PC fraco. */
"use strict";

const Hud = (() => {
  const CORES = {
    pronto: [63, 216, 255], ouvindo: [80, 230, 255], pensando: [122, 140, 255],
    executando: [255, 190, 70], falando: [70, 240, 200], erro: [255, 92, 122],
  };
  const ROTULOS = { pronto: "PRONTO", ouvindo: "OUVINDO", pensando: "PROCESSANDO",
    executando: "EXECUTANDO", falando: "FALANDO", erro: "ERRO" };

  let canvas = null; let ctx = null; let tamanho = 0;
  let estado = "pronto"; let cor = CORES.pronto.slice(); let alvoCor = CORES.pronto;
  let nivel = 0; let nivelSuave = 0; let ultimoNivel = 0;
  let ultimoQuadro = 0; let angulo = 0;
  const emblema = new Image(); emblema.src = "/emblema.png";

  function rgba(c, a) { return `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`; }

  function ajustar() {
    if (!canvas) return;
    const lado = Math.max(120, Math.min(canvas.clientWidth || 320, canvas.clientHeight || 320));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (tamanho !== lado * dpr) {
      tamanho = lado * dpr;
      canvas.width = tamanho; canvas.height = tamanho;
    }
  }

  function arco(r, ini, fim, largura, estilo) {
    ctx.beginPath(); ctx.arc(0, 0, r, ini, fim);
    ctx.lineWidth = largura; ctx.strokeStyle = estilo; ctx.stroke();
  }

  function desenhar(t) {
    requestAnimationFrame(desenhar);
    if (!canvas || document.hidden || !canvas.offsetParent) return;
    if (t - ultimoQuadro < 30) return; // ~30 quadros por segundo bastam
    const dt = Math.min(0.1, (t - ultimoQuadro) / 1000); ultimoQuadro = t;
    ajustar();
    // O nível de som some sozinho se ninguém atualizar.
    if (t - ultimoNivel > 250) nivel *= 0.85;
    nivelSuave += (nivel - nivelSuave) * 0.25;
    for (let i = 0; i < 3; i++) cor[i] += (alvoCor[i] - cor[i]) * 0.12;
    const veloc = { pensando: 2.2, executando: 1.6, falando: 1.2, ouvindo: 0.9 }[estado] || 0.45;
    angulo += dt * veloc;

    const S = tamanho; const R = S / 2; const n = nivelSuave;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, S, S);
    ctx.translate(R, R);

    // Brilho de fundo
    const fundo = ctx.createRadialGradient(0, 0, R * 0.1, 0, 0, R);
    fundo.addColorStop(0, rgba(cor, 0.22 + n * 0.25)); fundo.addColorStop(0.55, rgba(cor, 0.05));
    fundo.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = fundo; ctx.fillRect(-R, -R, S, S);

    // Anel externo com marcações
    ctx.save(); ctx.rotate(angulo * 0.15);
    const rExt = R * 0.94;
    for (let i = 0; i < 120; i++) {
      const a = (i / 120) * Math.PI * 2; const longo = i % 10 === 0;
      const r1 = rExt - (longo ? R * 0.05 : R * 0.022);
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1); ctx.lineTo(Math.cos(a) * rExt, Math.sin(a) * rExt);
      ctx.lineWidth = longo ? S * 0.004 : S * 0.0022; ctx.strokeStyle = rgba(cor, longo ? 0.8 : 0.35); ctx.stroke();
    }
    ctx.restore();
    arco(R * 0.865, 0, Math.PI * 2, S * 0.002, rgba(cor, 0.25));

    // Anel segmentado (gira ao contrário)
    ctx.save(); ctx.rotate(-angulo * 0.4);
    const segs = 14; const vao = 0.07;
    for (let i = 0; i < segs; i++) {
      const a = (i / segs) * Math.PI * 2;
      const forte = i % 3 === 0;
      arco(R * 0.79, a + vao, a + (Math.PI * 2) / segs - vao, S * (forte ? 0.022 : 0.012), rgba(cor, forte ? 0.75 : 0.4));
    }
    ctx.restore();

    // Arco âmbar (destaque, como nas referências)
    ctx.save(); ctx.rotate(angulo * 0.9);
    arco(R * 0.705, 0, Math.PI * 0.42, S * 0.009, `rgba(255,176,60,${0.55 + n * 0.4})`);
    arco(R * 0.705, Math.PI, Math.PI * 1.12, S * 0.009, "rgba(255,176,60,.45)");
    ctx.restore();

    // Anel tracejado interno
    ctx.save(); ctx.rotate(angulo * 0.6);
    ctx.setLineDash([S * 0.006, S * 0.012]);
    arco(R * 0.64, 0, Math.PI * 2, S * 0.006, rgba(cor, 0.55));
    ctx.setLineDash([]);
    ctx.restore();

    // Barras radiais que reagem à voz (ouvindo / falando)
    const barras = 72; const rBase = R * 0.5;
    for (let i = 0; i < barras; i++) {
      const a = (i / barras) * Math.PI * 2 + angulo * 0.2;
      const onda = 0.5 + 0.5 * Math.sin(i * 0.9 + t / 160) * Math.sin(i * 0.37 - t / 230);
      const alt = R * (0.02 + n * 0.11 * onda + (estado === "pensando" ? 0.03 * onda : 0));
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * rBase, Math.sin(a) * rBase);
      ctx.lineTo(Math.cos(a) * (rBase + alt), Math.sin(a) * (rBase + alt));
      ctx.lineWidth = S * 0.005; ctx.strokeStyle = rgba(cor, 0.35 + n * 0.6); ctx.stroke();
    }

    // Núcleo brilhante com o emblema
    const pulso = estado === "pensando" ? 0.04 * Math.sin(t / 180) : 0;
    const rNucleo = R * (0.4 + n * 0.05 + pulso);
    const nucleo = ctx.createRadialGradient(0, 0, rNucleo * 0.2, 0, 0, rNucleo * 1.25);
    nucleo.addColorStop(0, rgba([255, 255, 255], 0.9)); nucleo.addColorStop(0.35, rgba(cor, 0.85));
    nucleo.addColorStop(0.8, rgba(cor, 0.18)); nucleo.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = nucleo; ctx.beginPath(); ctx.arc(0, 0, rNucleo * 1.25, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(0, 0, rNucleo * 0.78, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(2,8,16,.88)"; ctx.fill();
    ctx.lineWidth = S * 0.006; ctx.strokeStyle = rgba(cor, 0.9); ctx.stroke();
    if (emblema.complete && emblema.naturalWidth) {
      ctx.save(); ctx.beginPath(); ctx.arc(0, 0, rNucleo * 0.74, 0, Math.PI * 2); ctx.clip();
      const l = rNucleo * 1.45; ctx.globalAlpha = 0.92;
      ctx.drawImage(emblema, -l / 2, -l / 2, l, l); ctx.restore();
    }
  }

  function iniciar(el) {
    if (canvas || !el) return;
    canvas = el; ctx = canvas.getContext("2d");
    window.addEventListener("resize", ajustar);
    requestAnimationFrame(desenhar);
  }

  function definirEstado(tipo) {
    if (!CORES[tipo]) tipo = "pronto";
    estado = tipo; alvoCor = CORES[tipo];
    const rotulo = document.getElementById("hud-estado");
    if (rotulo) { rotulo.textContent = ROTULOS[tipo]; rotulo.dataset.estado = tipo; }
  }

  function definirNivel(valor) { nivel = Math.max(nivel * 0.6, Math.min(1, valor)); ultimoNivel = performance.now(); }

  // Sequência de abertura: uma vez por sessão do navegador.
  function boot() {
    const tela = document.getElementById("boot");
    if (!tela) return Promise.resolve();
    let ja = false;
    try { ja = sessionStorage.getItem("optimus_boot") === "1"; sessionStorage.setItem("optimus_boot", "1"); } catch (e) {}
    if (ja || window.matchMedia("(prefers-reduced-motion: reduce)").matches) { tela.remove(); return Promise.resolve(); }
    const linhas = ["Inicializando núcleo neural", "Carregando memória local", "Conectando motor de IA",
      "Calibrando sensores de voz", "Sistemas online"];
    const lista = document.getElementById("boot-linhas");
    return new Promise((resolve) => {
      linhas.forEach((l, i) => setTimeout(() => {
        const li = document.createElement("li"); li.textContent = "› " + l; lista.appendChild(li);
      }, 180 + i * 260));
      setTimeout(() => { tela.classList.add("saindo"); }, 1700);
      setTimeout(() => { tela.remove(); resolve(); }, 2200);
    });
  }

  function relogio() {
    const el = document.getElementById("hud-relogio");
    const tique = () => {
      if (el) el.textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    };
    tique(); setInterval(tique, 15000);
  }

  // Gráfico de linha simples (histórico de CPU no painel)
  function grafico(el, valores, corLinha = "#3fd8ff") {
    if (!el) return;
    const c = el.getContext("2d"); const w = el.width; const h = el.height;
    c.clearRect(0, 0, w, h);
    c.strokeStyle = "rgba(63,216,255,.12)"; c.lineWidth = 1;
    for (let y = 0; y <= 4; y++) { c.beginPath(); c.moveTo(0, (h / 4) * y); c.lineTo(w, (h / 4) * y); c.stroke(); }
    if (valores.length < 2) return;
    const passo = w / (valores.length - 1);
    c.beginPath();
    valores.forEach((v, i) => { const y = h - (Math.min(100, v) / 100) * (h - 4) - 2; if (i) c.lineTo(i * passo, y); else c.moveTo(0, y); });
    c.strokeStyle = corLinha; c.lineWidth = 2; c.stroke();
    c.lineTo(w, h); c.lineTo(0, h); c.closePath();
    const g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "rgba(63,216,255,.28)"); g.addColorStop(1, "rgba(63,216,255,0)");
    c.fillStyle = g; c.fill();
  }

  // Anel de medição em SVG (CPU, RAM, tokens/s)
  function anel(id, fracao, texto) {
    const el = document.getElementById(id); if (!el) return;
    const valor = el.querySelector(".valor"); const circ = 2 * Math.PI * 15.5;
    valor.style.strokeDasharray = `${circ}`;
    valor.style.strokeDashoffset = `${circ * (1 - Math.max(0, Math.min(1, fracao)))}`;
    el.classList.toggle("alto", fracao > 0.85);
    el.querySelector("b").textContent = texto;
  }

  return { iniciar, estado: definirEstado, nivel: definirNivel, boot, relogio, grafico, anel,
    get atual() { return estado; } };
})();
