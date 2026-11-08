/* Voz ao vivo do Optimus: fala frase por frase, escuta contínua e palmas.
 *
 * Fala: cada frase pronta da resposta (mesmo antes do fim, com streaming) vira um pedido
 * /api/falar (Kokoro, Edge, ElevenLabs ou voz do sistema, no PC). As frases tocam em fila;
 * a próxima é gerada enquanto a atual toca. Se o servidor não conseguir falar, usa a voz do
 * próprio navegador, para nunca ficar mudo.
 *
 * Escuta: usa o reconhecimento de voz do navegador (Chrome/Edge, contínuo, em pt-BR). Sem
 * ele (Firefox, Chromium sem serviço de voz), grava cada fala detectada pelo volume e
 * transcreve no PC com o Whisper (/api/ouvir). O detector de palmas roda no próprio
 * navegador, sobre o áudio do microfone.
 */
"use strict";

const Voz = (() => {
  const ev = { onTexto: null, onNivel: null, onPalmas: null, onEstado: null, onErro: null, onFimFala: null };
  const config = { api: null, sensibilidade: 1.0, palmas: true };
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

  let ctx = null;
  function audioCtx() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) ctx = new AC();
    }
    if (ctx && ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  // ------------------------------------------------------------------ FALA
  const fila = [];
  let tocando = false, audio = null, buffer = "", emCodigo = false, geracao = 0;

  function limparParaFala(t) {
    return String(t || "")
      .replace(/```[\s\S]*?```/g, " (o código está na tela) ")
      .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
      .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, "$1")
      .replace(/https?:\/\/\S+/g, " link ")
      .replace(/[*_#`>|~]+/g, " ")
      .replace(/\s+/g, " ").trim();
  }

  async function buscarAudio(texto) {
    const r = await config.api("/api/falar", { method: "POST", json: { texto } });
    if (!r || typeof r.blob !== "function") throw new Error("sem áudio");
    return await r.blob();
  }
  function garantirBusca(item) {
    if (item && !item.blob) item.blob = buscarAudio(item.texto).catch((e) => { item.erro = e; return null; });
  }

  function falarNavegador(texto) {
    return new Promise((resolve) => {
      if (!("speechSynthesis" in window)) return resolve();
      const u = new SpeechSynthesisUtterance(texto);
      u.lang = "pt-BR";
      const voz = speechSynthesis.getVoices().find((v) => /pt[-_]BR/i.test(v.lang));
      if (voz) u.voice = voz;
      u.onend = u.onerror = () => resolve();
      speechSynthesis.speak(u);
      const pulso = setInterval(() => { if (!speechSynthesis.speaking) { clearInterval(pulso); resolve(); } nivelFala(0.35 + Math.random() * 0.4); }, 120);
    });
  }

  let nivelTimer = null;
  function nivelFala(n) { if (ev.onNivel) ev.onNivel("fala", n); }

  async function tocarBlob(blob, minhaGeracao) {
    return new Promise((resolve) => {
      if (minhaGeracao !== geracao) return resolve();
      audio = new Audio(URL.createObjectURL(blob));
      const c = audioCtx();
      let analisador = null;
      try {
        if (c) {
          const fonte = c.createMediaElementSource(audio);
          analisador = c.createAnalyser(); analisador.fftSize = 512;
          fonte.connect(analisador); analisador.connect(c.destination);
        }
      } catch (e) { analisador = null; }
      const dados = new Float32Array(512);
      clearInterval(nivelTimer);
      nivelTimer = setInterval(() => {
        if (!analisador) return nivelFala(0.5);
        analisador.getFloatTimeDomainData(dados);
        let s = 0; for (const v of dados) s += v * v;
        nivelFala(Math.min(1, Math.sqrt(s / dados.length) * 6));
      }, 60);
      const fim = () => { clearInterval(nivelTimer); nivelFala(0); resolve(); };
      audio.onended = fim; audio.onerror = fim; audio.onpause = () => { if (minhaGeracao !== geracao) fim(); };
      audio.play().catch(fim);
    });
  }

  async function tocarProxima() {
    if (tocando || !fila.length) return;
    tocando = true;
    const minhaGeracao = geracao;
    if (ev.onEstado) ev.onEstado("falando");
    while (fila.length && minhaGeracao === geracao) {
      const item = fila.shift();
      garantirBusca(item);
      garantirBusca(fila[0]);
      const blob = await item.blob;
      if (minhaGeracao !== geracao) break;
      if (blob && blob.size > 200) await tocarBlob(blob, minhaGeracao);
      else await falarNavegador(item.texto);
    }
    tocando = false;
    if (minhaGeracao === geracao && !fila.length && ev.onFimFala) ev.onFimFala();
  }

  function enfileirar(frase) {
    const texto = limparParaFala(frase);
    if (texto.length < 2) return;
    const item = { texto, blob: null };
    fila.push(item);
    if (fila.length <= 2) garantirBusca(item);
    tocarProxima();
  }

  // Recebe a resposta aos pedaços e fala cada frase assim que ela termina.
  function adicionarParcial(pedaco) {
    buffer += pedaco;
    while (true) {
      const cerca = buffer.indexOf("```");
      if (emCodigo) {
        if (cerca < 0) return;
        buffer = buffer.slice(cerca + 3); emCodigo = false; enfileirar("O código está na tela."); continue;
      }
      const m = buffer.match(/^([\s\S]*?[.!?…:;])(\s+)|^([^\n]*\n)/);
      if (cerca >= 0 && (!m || cerca < m[0].length)) {
        enfileirar(buffer.slice(0, cerca)); buffer = buffer.slice(cerca + 3); emCodigo = true; continue;
      }
      if (!m) return;
      const frase = (m[1] || m[3] || "").trim();
      if (frase.length < 12 && buffer.length < 200 && m[1]) {
        // frase muito curta: junta com a próxima para soar natural
        const resto = buffer.slice(m[0].length);
        const prox = resto.match(/^([\s\S]*?[.!?…:;])(\s+)/);
        if (!prox) return;
        enfileirar(frase + " " + prox[1]);
        buffer = resto.slice(prox[0].length);
        continue;
      }
      enfileirar(frase);
      buffer = buffer.slice(m[0].length);
    }
  }
  function finalizar() {
    if (!emCodigo && buffer.trim()) enfileirar(buffer);
    buffer = ""; emCodigo = false;
    if (!tocando && !fila.length && ev.onFimFala) ev.onFimFala();
  }
  function falar(texto) {
    parar();
    adicionarParcial(String(texto || "") + "\n");
    finalizar();
  }
  function parar() {
    geracao++;
    fila.length = 0; buffer = ""; emCodigo = false;
    if (audio) { try { audio.pause(); } catch (e) {} }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    clearInterval(nivelTimer); nivelFala(0);
    tocando = false;
  }
  const falando = () => tocando || fila.length > 0;

  // ------------------------------------------------------------------ MICROFONE
  let fluxo = null, analisadorMic = null, laco = null;
  let escutando = false, reconhecedor = null, modo = "nenhum";

  async function abrirMicrofone() {
    if (fluxo) return fluxo;
    fluxo = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    const c = audioCtx();
    if (c) {
      const fonte = c.createMediaStreamSource(fluxo);
      analisadorMic = c.createAnalyser(); analisadorMic.fftSize = 2048;
      fonte.connect(analisadorMic);
      monitorar();
    }
    return fluxo;
  }
  function fecharMicrofone() {
    cancelAnimationFrame(laco);
    if (fluxo) fluxo.getTracks().forEach((t) => t.stop());
    fluxo = null; analisadorMic = null;
  }

  // Detector de palmas: pico alto e curto (som "seco") duas vezes, com 0,15 a 0,9 s entre elas.
  const palmas = { picos: [], ultimo: 0, piso: 0.01, anteriorRms: 0 };
  function detectarPalma(pico, rms, agora) {
    if (!config.palmas) return;
    const s = config.sensibilidade || 1;
    const subita = rms > palmas.anteriorRms * 3 + 0.01;
    const seca = pico / Math.max(rms, 1e-4) > 4.5;
    if (pico > 0.32 / s && subita && seca && agora - (palmas.picos[palmas.picos.length - 1] || 0) > 120) {
      palmas.picos = palmas.picos.filter((t) => agora - t < 1000);
      const anterior = palmas.picos[palmas.picos.length - 1];
      palmas.picos.push(agora);
      if (anterior && agora - anterior >= 150 && agora - anterior <= 900 && agora - palmas.ultimo > 2000) {
        palmas.ultimo = agora; palmas.picos = [];
        if (ev.onPalmas) ev.onPalmas();
      }
    }
  }

  // Gravação por volume (modo Whisper)
  const vad = { gravador: null, pedacos: [], falando: false, silencioDesde: 0, inicio: 0 };
  function vadPasso(rms, agora) {
    if (modo !== "whisper" || !escutando) return;
    const limiar = Math.max(0.018 / (config.sensibilidade || 1), palmas.piso * 3.2);
    if (falando()) return; // não grava a própria voz do Optimus
    if (rms > limiar) {
      vad.silencioDesde = 0;
      if (!vad.gravador) {
        try {
          vad.gravador = new MediaRecorder(fluxo); vad.pedacos = []; vad.inicio = agora;
          vad.gravador.ondataavailable = (e) => vad.pedacos.push(e.data);
          vad.gravador.onstop = enviarGravacao;
          vad.gravador.start();
        } catch (e) { vad.gravador = null; }
      }
    } else if (vad.gravador) {
      if (!vad.silencioDesde) vad.silencioDesde = agora;
      if (agora - vad.silencioDesde > 900 || agora - vad.inicio > 15000) {
        const g = vad.gravador; vad.gravador = null; g.stop();
      }
    }
  }
  async function enviarGravacao() {
    const blob = new Blob(vad.pedacos, { type: "audio/webm" });
    if (blob.size < 3000) return;
    try {
      const d = await config.api("/api/ouvir", { method: "POST", body: blob });
      if (d && d.texto && ev.onTexto) ev.onTexto(d.texto, true);
    } catch (e) { if (ev.onErro) ev.onErro("Reconhecimento de voz falhou: " + e.message); }
  }

  function monitorar() {
    const dados = new Float32Array(2048);
    const passo = () => {
      laco = requestAnimationFrame(passo);
      if (!analisadorMic) return;
      analisadorMic.getFloatTimeDomainData(dados);
      let soma = 0, pico = 0;
      for (const v of dados) { soma += v * v; const a = Math.abs(v); if (a > pico) pico = a; }
      const rms = Math.sqrt(soma / dados.length);
      const agora = performance.now();
      palmas.piso = palmas.piso * 0.995 + Math.min(rms, 0.05) * 0.005;
      detectarPalma(pico, rms, agora);
      palmas.anteriorRms = rms;
      vadPasso(rms, agora);
      if (ev.onNivel && !falando()) ev.onNivel("mic", Math.min(1, rms * 9));
    };
    passo();
  }

  // ------------------------------------------------------------------ ESCUTA CONTÍNUA
  function iniciarReconhecedor() {
    reconhecedor = new SR();
    reconhecedor.lang = "pt-BR";
    reconhecedor.continuous = true;
    reconhecedor.interimResults = true;
    reconhecedor.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (ev.onTexto) ev.onTexto(r[0].transcript, r.isFinal);
      }
    };
    reconhecedor.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        if (e.error === "service-not-allowed" || !fluxo) { modo = "whisper"; if (ev.onErro) ev.onErro("O navegador não liberou o reconhecimento de voz dele; usando o Whisper do PC."); }
        else { escutando = false; if (ev.onErro) ev.onErro("Microfone bloqueado. Libere o microfone no cadeado da barra de endereço."); }
      } else if (e.error === "network" || e.error === "language-not-supported") {
        modo = "whisper";
        if (ev.onErro) ev.onErro("Reconhecimento do navegador indisponível (sem serviço de voz). Usando o Whisper do PC.");
      }
    };
    reconhecedor.onend = () => {
      if (escutando && modo === "navegador") setTimeout(() => { try { reconhecedor.start(); } catch (e) {} }, 200);
    };
    reconhecedor.start();
  }

  async function iniciarEscuta(preferirWhisper = false) {
    audioCtx();
    escutando = true;
    try { await abrirMicrofone(); } catch (e) {
      escutando = false;
      if (ev.onErro) ev.onErro("Não consegui abrir o microfone: " + e.message + ". Libere o microfone para este site.");
      return false;
    }
    if (SR && !preferirWhisper) { modo = "navegador"; try { iniciarReconhecedor(); } catch (e) { modo = "whisper"; } }
    else modo = "whisper";
    if (ev.onEstado) ev.onEstado("ouvindo");
    return true;
  }
  function pararEscuta() {
    escutando = false;
    if (reconhecedor) { try { reconhecedor.onend = null; reconhecedor.stop(); } catch (e) {} reconhecedor = null; }
    if (vad.gravador) { try { vad.gravador.stop(); } catch (e) {} vad.gravador = null; }
    fecharMicrofone();
    modo = "nenhum";
  }

  // Gravação manual (botão do microfone): devolve o texto reconhecido.
  async function gravarUmaVez(segundosMax = 12) {
    if (SR) {
      return new Promise((resolve, reject) => {
        const r = new SR(); r.lang = "pt-BR"; r.interimResults = true; r.continuous = false;
        let final = "";
        r.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i++) { if (e.results[i].isFinal) final += e.results[i][0].transcript; else if (ev.onTexto) ev.onTexto(e.results[i][0].transcript, false); } };
        r.onerror = (e) => { if (e.error === "no-speech") resolve(""); else reject(new Error(e.error)); };
        r.onend = () => resolve(final.trim());
        r.start();
        setTimeout(() => { try { r.stop(); } catch (e) {} }, segundosMax * 1000);
      });
    }
    const f = await navigator.mediaDevices.getUserMedia({ audio: true });
    return new Promise((resolve, reject) => {
      const g = new MediaRecorder(f); const partes = [];
      g.ondataavailable = (e) => partes.push(e.data);
      g.onstop = async () => {
        f.getTracks().forEach((t) => t.stop());
        try { const d = await config.api("/api/ouvir", { method: "POST", body: new Blob(partes, { type: g.mimeType }) }); resolve(d.texto || ""); }
        catch (e) { reject(e); }
      };
      g.start();
      Voz._pararGravacao = () => { if (g.state === "recording") g.stop(); };
      setTimeout(Voz._pararGravacao, segundosMax * 1000);
    });
  }

  return {
    ev, config, falar, adicionarParcial, finalizar, parar, falando, iniciarEscuta, pararEscuta,
    gravarUmaVez, audioCtx, limparParaFala,
    get escutando() { return escutando; }, get modo() { return modo; },
    temReconhecimentoNavegador: !!SR, _pararGravacao: null,
  };
})();
