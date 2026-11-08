/* Interface do Optimus. Sem dependências externas: funciona offline. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const app = $("#app");
const boasVindas = $("#boas-vindas");

const estado = {
  conversa: 0, persona: "optimus", personas: [], falar: false, grupo: false,
  config: null, vozes: [], ocupado: false, projeto: "", conversas: [], nome: "Optimus",
};
try { estado.falar = localStorage.getItem("optimus_falar") === "1"; } catch (e) {}

// ---------- API ----------
let senha = "";
try { senha = sessionStorage.getItem("optimus_senha") || ""; } catch (e) {}

async function api(caminho, opcoes = {}) {
  const cab = Object.assign({}, opcoes.headers || {});
  if (senha) cab["X-Optimus-Senha"] = senha;
  if (opcoes.json !== undefined) { cab["Content-Type"] = "application/json"; opcoes.body = JSON.stringify(opcoes.json); }
  const r = await fetch(caminho, Object.assign({}, opcoes, { headers: cab }));
  if (r.status === 401) { pedirSenha(); throw new Error("senha"); }
  const tipo = r.headers.get("Content-Type") || "";
  if (tipo.includes("json")) {
    const dados = await r.json();
    if (!r.ok) throw new Error(dados.erro || r.statusText);
    return dados;
  }
  if (!r.ok) throw new Error(r.statusText);
  return r;
}

function pedirSenha() {
  $("#modal-senha").classList.remove("oculto");
}
$("#form-senha").addEventListener("submit", async (e) => {
  e.preventDefault();
  senha = e.target.senha.value;
  const r = await fetch("/api/entrar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ senha }) });
  if (r.ok) {
    try { sessionStorage.setItem("optimus_senha", senha); } catch (err) {}
    $("#modal-senha").classList.add("oculto");
    iniciar();
  } else { e.target.senha.value = ""; e.target.senha.placeholder = "Senha errada"; }
});

// ---------- Utilidades ----------
function esc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function markdown(texto) {
  const blocos = [];
  let t = String(texto || "").replace(/```(\w*)\n?([\s\S]*?)```/g, (_, l, c) => { blocos.push(c); return `\u0000${blocos.length - 1}\u0000`; });
  t = esc(t)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>')
    .replace(/^#{1,4} (.+)$/gm, "<strong>$1</strong>");
  const linhas = t.split("\n"); let html = ""; let lista = null;
  for (const linha of linhas) {
    const item = linha.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)/);
    if (item) {
      const tipo = item[1] ? "ol" : "ul";
      if (lista !== tipo) { if (lista) html += `</${lista}>`; html += `<${tipo}>`; lista = tipo; }
      html += `<li>${item[2]}</li>`; continue;
    }
    if (lista) { html += `</${lista}>`; lista = null; }
    html += linha.trim() ? `<p>${linha}</p>` : "";
  }
  if (lista) html += `</${lista}>`;
  return html.replace(/\u0000(\d+)\u0000/g, (_, i) => `<pre><code>${esc(blocos[i])}</code></pre>`);
}
function quando(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
function definirEstado(tipo, texto) {
  $("#orbe").className = "orbe " + tipo;
  $("#estado-texto").textContent = texto;
}

// ---------- Navegação ----------
function irPara(tela) {
  $$(".menu button").forEach((b) => b.classList.toggle("ativo", b.dataset.tela === tela));
  $$(".tela").forEach((t) => t.classList.toggle("ativa", t.id === "tela-" + tela));
  app.classList.remove("lateral-aberta");
  const carregar = { personas: carregarPersonas, prompts: carregarPrompts, memoria: carregarMemoria, acoes: carregarAcoes, config: carregarConfig, casa: carregarCasa }[tela];
  if (carregar) carregar();
}
$$(".menu button").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.tela)));
$("#abrir-lateral").onclick = () => app.classList.add("lateral-aberta");
$("#fechar-lateral").onclick = () => app.classList.remove("lateral-aberta");
$("#alternar-painel").onclick = () => {
  if (window.innerWidth <= 1100) app.classList.toggle("com-painel");
  else app.classList.toggle("sem-painel");
};

// ---------- Estado do sistema ----------
async function atualizarSistema() {
  try {
    const d = await api("/api/estado");
    $("#versao").textContent = "v" + d.versao + " · " + d.perfil.nome;
    estado.nome = d.nome || "Optimus"; boasVindas.querySelector("#nome-assistente").textContent = estado.nome;
    const m = d.motor;
    $("#modelo-texto").innerHTML = `<span class="ponto ${m.disponivel ? "on" : ""}"></span>${esc(m.modelo || "sem modelo")} · ${esc(m.backend)}${m.disponivel ? "" : " (desligado)"}`;
    const modo = $("#modo"); modo.textContent = d.modo; modo.className = "selo " + d.modo;
    for (const [id, valor] of [["cpu", d.uso.cpu], ["ram", d.uso.ram]]) {
      const barra = $("#" + id + "-barra"); barra.style.width = valor + "%"; barra.classList.toggle("alto", valor > 85);
      $("#" + id + "-valor").textContent = Math.round(valor) + "%";
    }
    const hw = d.hardware;
    $("#hw-info").innerHTML = [
      ["Sistema", `${hw.sistema} ${hw.versao_sistema}`], ["CPU", hw.cpu], ["Núcleos", `${hw.nucleos_fisicos} / ${hw.nucleos_logicos} threads`],
      ["RAM", `${hw.ram_total_gb} GB (${d.uso.ram_livre_gb} livre)`], ["Vídeo", hw.placa ? `${hw.placa.nome} (${hw.placa.vram_gb} GB)` : "integrada / nenhuma"],
      ["Perfil", d.perfil.nome],
    ].map(([a, b]) => `<div><span>${a}</span><span>${esc(b)}</span></div>`).join("");
    let motorHtml = [["Motor", m.backend], ["Modelo", m.modelo], ["Rápido", d.perfil.modelo_rapido], ["Contexto", d.perfil.contexto + " tokens"], ["Modelos instalados", m.modelos.length]]
      .map(([a, b]) => `<div><span>${a}</span><span>${esc(b)}</span></div>`).join("");
    if (m.destinos.length) motorHtml += m.destinos.map((x) => `<div><span><span class="ponto ${x.ligado ? "on" : ""}"></span>${esc(x.nome)}</span><span>${esc(x.modelo || "padrão")}</span></div>`).join("");
    $("#motor-info").innerHTML = motorHtml;
    $("#modelos-lista").innerHTML = m.modelos.map((x) => `<option value="${esc(x)}">`).join("");
    $("#perfil-hardware").textContent = d.resumo;
    $("#avisos").innerHTML = d.avisos.length ? d.avisos.slice().reverse().map((a) => `<li><span>⏰ ${esc(a.texto)}</span><small>${quando(a.quando)}</small></li>`).join("") : '<li class="sutil">Nenhum aviso</li>';
    mostrarLembretes(d.avisos);
  } catch (e) { if (e.message !== "senha") definirEstado("erro", "Sem conexão com o Optimus"); }
}
const avisados = new Set();
function mostrarLembretes(avisos) {
  for (const a of avisos) {
    const chave = a.texto + a.quando;
    if (avisados.has(chave)) continue;
    avisados.add(chave);
    if (Date.now() / 1000 - a.quando > 60) continue;
    if ("Notification" in window && Notification.permission === "granted") new Notification("Optimus", { body: a.texto, icon: "/logo.svg" });
    adicionarMensagem("optimus", `⏰ **Lembrete:** ${a.texto}`, { nome: "Lembrete" });
    if (estado.falar) falar("Lembrete: " + a.texto);
  }
}

// ---------- Conversas ----------
async function carregarConversas() {
  const d = await api("/api/conversas");
  estado.conversas = d.conversas;
  const filtro = $("#filtro-projeto");
  const atual = filtro.value;
  filtro.innerHTML = '<option value="">Todos os projetos</option>' + d.projetos.map((p) => `<option ${p === atual ? "selected" : ""}>${esc(p)}</option>`).join("");
  desenharConversas();
}
function desenharConversas() {
  const busca = $("#busca").value.toLowerCase(); const projeto = $("#filtro-projeto").value;
  const itens = estado.conversas.filter((c) => (!projeto || c.projeto === projeto) && c.titulo.toLowerCase().includes(busca));
  $("#lista-conversas").innerHTML = itens.map((c) => `<li data-id="${c.id}" class="${c.id === estado.conversa ? "ativo" : ""}">
      <div style="min-width:0"><span>${esc(c.titulo)}</span><small>${c.projeto ? "📁 " + esc(c.projeto) + " · " : ""}${quando(c.atualizada)}</small></div>
      <div><button data-projeto="${c.id}" title="Mover para projeto">📁</button><button data-apagar="${c.id}" title="Apagar">🗑️</button></div></li>`).join("")
    || '<li class="sutil">Nenhuma conversa ainda</li>';
}
$("#busca").addEventListener("input", desenharConversas);
$("#filtro-projeto").addEventListener("change", desenharConversas);
$("#lista-conversas").addEventListener("click", async (e) => {
  const apagar = e.target.closest("[data-apagar]"); const projeto = e.target.closest("[data-projeto]");
  if (apagar) {
    e.stopPropagation();
    if (!confirm("Apagar esta conversa?")) return;
    await api("/api/conversas/" + apagar.dataset.apagar, { method: "DELETE" });
    if (+apagar.dataset.apagar === estado.conversa) novaConversa();
    return carregarConversas();
  }
  if (projeto) {
    e.stopPropagation();
    const nome = prompt("Nome do projeto (vazio remove):", "");
    if (nome === null) return;
    await api("/api/conversas/" + projeto.dataset.projeto, { method: "POST", json: { projeto: nome.trim() } });
    return carregarConversas();
  }
  const li = e.target.closest("li[data-id]");
  if (li) abrirConversa(+li.dataset.id);
});

async function abrirConversa(id) {
  irPara("chat");
  estado.conversa = id;
  const d = await api(`/api/conversas/${id}/mensagens`);
  $("#mensagens").innerHTML = "";
  if (d.conversa && d.conversa.persona) { estado.persona = d.conversa.persona; $("#persona").value = d.conversa.persona; }
  for (const m of d.mensagens) {
    if (m.papel === "user") adicionarMensagem("usuario", m.conteudo);
    else if (m.papel === "assistant") adicionarMensagem("optimus", m.conteudo, m.extra);
  }
  desenharConversas();
}
function novaConversa() {
  estado.conversa = 0;
  $("#mensagens").innerHTML = "";
  $("#mensagens").appendChild(boasVindas);
  irPara("chat");
  desenharConversas();
  $("#entrada").focus();
}
$("#nova-conversa").onclick = novaConversa;
boasVindas.addEventListener("click", (e) => {
  const b = e.target.closest("[data-sugestao]");
  if (b) { $("#entrada").value = b.dataset.sugestao; enviar(); }
});

function adicionarMensagem(quem, texto, extra = {}) {
  if (boasVindas.parentNode) boasVindas.remove();
  const div = document.createElement("div");
  div.className = "msg " + quem;
  const nome = quem === "usuario" ? "Você" : extra.nome || nomePersona(extra.persona) || estado.nome;
  const detalhes = extra.segundos ? ` · ${extra.segundos}s` : "";
  div.innerHTML = `<div class="avatar">${quem === "usuario" ? "🙂" : "◉"}</div><div class="corpo">
    <div class="quem">${esc(nome)}${detalhes}${quem !== "usuario" ? ' <button title="Ouvir">🔊</button><button title="Copiar">📋</button>' : ""}</div>
    <div class="passos"></div><div class="texto"></div></div>`;
  const alvo = $(".texto", div);
  if (quem === "usuario") alvo.textContent = texto; else alvo.innerHTML = markdown(texto);
  const [ouvir, copiar] = $$(".quem button", div);
  if (ouvir) ouvir.onclick = () => falar(texto);
  if (copiar) copiar.onclick = () => navigator.clipboard && navigator.clipboard.writeText(texto);
  $("#mensagens").appendChild(div);
  $("#mensagens").scrollTop = $("#mensagens").scrollHeight;
  return div;
}
function nomePersona(chave) {
  const p = estado.personas.find((x) => x.chave === chave);
  return p && chave !== "optimus" ? p.nome : "";
}

// ---------- Enviar e acompanhar ----------
async function enviar(textoVoz) {
  const entrada = $("#entrada");
if (window.innerWidth <= 760) entrada.placeholder = "Fale com o Optimus…";
  const texto = (textoVoz || entrada.value).trim();
  if (!texto || estado.ocupado) return;
  entrada.value = ""; ajustarEntrada();
  estado.ocupado = true;
  adicionarMensagem("usuario", texto);
  const resposta = adicionarMensagem("optimus", "", { persona: estado.persona });
  $(".texto", resposta).innerHTML = '<div class="digitando"><span></span><span></span><span></span></div>';
  definirEstado("pensando", "Pensando…");
  const grupo = estado.grupo ? $$("#grupo-escolha input:checked").map((i) => i.value) : null;
  try {
    const { tarefa } = await api("/api/enviar", { method: "POST", json: { conversa: estado.conversa, texto, persona: estado.persona, grupo: grupo && grupo.length ? grupo : null, voz: !!textoVoz, projeto: $("#filtro-projeto").value } });
    await acompanhar(tarefa, resposta);
  } catch (e) {
    if (e.message !== "senha") $(".texto", resposta).innerHTML = `<p>⚠️ ${esc(e.message)}</p>`;
  }
  estado.ocupado = false;
  definirEstado("pronto", "Pronto");
  carregarConversas();
}

async function acompanhar(tarefa, bolha) {
  let desde = 0; let pendenteMostrado = false; let atual = bolha; let primeiraFinal = true;
  while (true) {
    const d = await api(`/api/tarefa/${tarefa}?desde=${desde}`);
    desde = d.total;
    for (const ev of d.eventos) {
      if (ev.tipo === "conversa") estado.conversa = ev.id;
      else if (ev.tipo === "pensando") definirEstado("pensando", ev.passo > 1 ? `Pensando (passo ${ev.passo})…` : "Pensando…");
      else if (ev.tipo === "ferramenta") {
        definirEstado("executando", "Executando " + ev.nome);
        const passo = document.createElement("details");
        passo.className = "passo";
        passo.innerHTML = `<summary>🔧 <b>${esc(ev.nome)}</b> <span class="nivel ${esc(ev.nivel)}">${esc(ev.nivel)}</span> <span class="sutil">${esc(resumoArgs(ev.argumentos))}</span></summary><pre></pre>`;
        $(".passos", atual).appendChild(passo);
      } else if (ev.tipo === "resultado") {
        const passos = $$(".passo pre", atual);
        if (passos.length) passos[passos.length - 1].textContent = bonito(ev.resultado);
      } else if (ev.tipo === "negada") {
        const passos = $$(".passo summary", atual);
        if (passos.length) passos[passos.length - 1].insertAdjacentHTML("beforeend", ' <span class="nivel bloqueado">negada</span>');
      } else if (ev.tipo === "aviso") {
        $(".passos", atual).insertAdjacentHTML("beforeend", `<div class="passo">⚠️ ${esc(ev.texto)}</div>`);
      } else if (ev.tipo === "final") {
        if (!primeiraFinal) atual = adicionarMensagem("optimus", "", ev);
        primeiraFinal = false;
        $(".texto", atual).innerHTML = markdown(ev.texto);
        $(".quem", atual).firstChild.textContent = ev.nome && ev.persona !== "optimus" ? ev.nome : estado.nome;
        $(".quem", atual).insertAdjacentHTML("beforeend", ` <span class="sutil">${ev.segundos}s</span>`);
        const [ouvir, copiar] = $$(".quem button", atual);
        ouvir.onclick = () => falar(ev.texto);
        copiar.onclick = () => navigator.clipboard && navigator.clipboard.writeText(ev.texto);
        if (estado.falar) falar(ev.texto);
      } else if (ev.tipo === "erro") {
        $(".texto", atual).innerHTML = `<p>⚠️ ${esc(ev.texto)}</p>`;
      }
      $("#mensagens").scrollTop = $("#mensagens").scrollHeight;
    }
    if (d.pendente && !pendenteMostrado) { pendenteMostrado = true; mostrarConfirmacao(tarefa, d.pendente, atual); }
    if (!d.pendente) pendenteMostrado = false;
    if (d.terminou) break;
    await new Promise((r) => setTimeout(r, 450));
  }
}
function resumoArgs(a) {
  const t = Object.entries(a || {}).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join(" · ");
  return t.length > 90 ? t.slice(0, 90) + "…" : t;
}
function bonito(t) { try { return JSON.stringify(JSON.parse(t), null, 2); } catch (e) { return t; } }

function mostrarConfirmacao(tarefa, p, bolha) {
  definirEstado("executando", "Aguardando sua confirmação");
  const critico = p.nivel >= 2;
  const div = document.createElement("div");
  div.className = "confirmacao" + (critico ? " critico" : "");
  div.innerHTML = `<h4>${critico ? "⛔ Ação crítica" : "⚠️ Confirmar ação"}</h4>
    <div>O Optimus quer <b>${esc(p.motivo)}</b>.</div><code>${esc(p.nome)}(${esc(JSON.stringify(p.argumentos, null, 1))})</code>
    <div class="linha"><button class="botao ${critico ? "perigo" : "primario"}" data-sim>Aprovar</button><button class="botao" data-nao>Negar</button></div>`;
  $(".passos", bolha).appendChild(div);
  if (estado.falar) falar(`Atenção. Posso ${p.motivo}?`);
  const responder = async (sim) => {
    $$("button", div).forEach((b) => (b.disabled = true));
    div.insertAdjacentHTML("beforeend", `<div class="sutil">${sim ? "✅ Aprovado por você" : "❌ Negado por você"}</div>`);
    await api("/api/confirmar", { method: "POST", json: { tarefa, aprovar: sim } });
  };
  $("[data-sim]", div).onclick = () => responder(true);
  $("[data-nao]", div).onclick = () => responder(false);
  $("#mensagens").scrollTop = $("#mensagens").scrollHeight;
}

// ---------- Entrada ----------
const entrada = $("#entrada");
function ajustarEntrada() { entrada.style.height = "auto"; entrada.style.height = Math.min(entrada.scrollHeight, 200) + "px"; }
entrada.addEventListener("input", ajustarEntrada);
entrada.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } });
$("#enviar").onclick = () => enviar();
const botaoFalar = $("#falar-respostas");
function desenharFalar() { botaoFalar.classList.toggle("ligado", estado.falar); botaoFalar.textContent = estado.falar ? "🔊" : "🔈"; }
botaoFalar.onclick = () => { estado.falar = !estado.falar; try { localStorage.setItem("optimus_falar", estado.falar ? "1" : "0"); } catch (e) {} desenharFalar(); };
desenharFalar();
$("#persona").addEventListener("change", (e) => { estado.persona = e.target.value; if (estado.conversa) api("/api/conversas/" + estado.conversa, { method: "POST", json: { persona: estado.persona } }); });
$("#alternar-grupo").onclick = () => {
  estado.grupo = !estado.grupo;
  $("#alternar-grupo").classList.toggle("ligado", estado.grupo);
  $("#grupo-barra").classList.toggle("oculto", !estado.grupo);
};

// ---------- Voz ----------
let audioAtual = null;
async function falar(texto) {
  try {
    if (audioAtual) audioAtual.pause();
    definirEstado("falando", "Falando…");
    const r = await api("/api/falar", { method: "POST", json: { texto } });
    const blob = await r.blob();
    audioAtual = new Audio(URL.createObjectURL(blob));
    audioAtual.onended = () => definirEstado("pronto", "Pronto");
    await audioAtual.play();
  } catch (e) { definirEstado("pronto", "Pronto"); }
}
let gravador = null; let pedacos = [];
async function comecarGravar() {
  if (gravador) return;
  if (audioAtual) audioAtual.pause();
  try {
    const fluxo = await navigator.mediaDevices.getUserMedia({ audio: true });
    gravador = new MediaRecorder(fluxo); pedacos = [];
    gravador.ondataavailable = (e) => pedacos.push(e.data);
    gravador.onstop = async () => {
      fluxo.getTracks().forEach((t) => t.stop());
      const blob = new Blob(pedacos, { type: gravador.mimeType }); gravador = null;
      $("#microfone").classList.remove("gravando");
      definirEstado("pensando", "Transcrevendo…");
      try {
        const d = await api("/api/ouvir", { method: "POST", body: blob });
        if (d.texto) enviar(d.texto); else definirEstado("pronto", "Não entendi, tente de novo");
      } catch (e) { definirEstado("erro", "Reconhecimento de voz indisponível"); }
    };
    gravador.start();
    $("#microfone").classList.add("gravando");
    definirEstado("ouvindo", "Ouvindo… solte para enviar");
  } catch (e) { definirEstado("erro", "Microfone bloqueado"); }
}
function pararGravar() { if (gravador && gravador.state === "recording") gravador.stop(); }
const mic = $("#microfone");
mic.addEventListener("pointerdown", (e) => { e.preventDefault(); comecarGravar(); });
mic.addEventListener("pointerup", pararGravar);
mic.addEventListener("pointerleave", pararGravar);

// ---------- Personas ----------
async function carregarPersonas() {
  const d = await api("/api/personas");
  estado.personas = d.personas;
  $("#persona").innerHTML = d.personas.map((p) => `<option value="${esc(p.chave)}" ${p.chave === estado.persona ? "selected" : ""}>${esc(p.nome)}</option>`).join("");
  $("#grupo-escolha").innerHTML = d.personas.map((p) => `<label><input type="checkbox" value="${esc(p.chave)}" ${["optimus", "pesquisador"].includes(p.chave) ? "checked" : ""}> ${esc(p.nome)}</label>`).join("");
  $("#lista-personas").innerHTML = d.personas.map((p) => `<div class="cartao item" data-chave="${esc(p.chave)}">
      <div class="acoes">${p.chave !== "optimus" ? `<button class="icone" data-apagar-persona="${esc(p.chave)}" title="Apagar">🗑️</button>` : ""}</div>
      <h3>🎭 ${esc(p.nome)}</h3><p>${esc(p.descricao || "")}</p><p>${esc((p.prompt || "usa a personalidade padrão").slice(0, 120))}</p>
      <p>${p.modelo ? "🧠 " + esc(p.modelo) : ""} ${p.voz ? "🔊 " + esc(p.voz) : ""}</p></div>`).join("");
}
$("#lista-personas").addEventListener("click", async (e) => {
  const apagar = e.target.closest("[data-apagar-persona]");
  if (apagar) { e.stopPropagation(); await api("/api/personas/" + apagar.dataset.apagarPersona, { method: "DELETE" }); return carregarPersonas(); }
  const item = e.target.closest("[data-chave]"); if (!item) return;
  const p = estado.personas.find((x) => x.chave === item.dataset.chave); const f = $("#form-persona");
  for (const k of ["chave", "nome", "descricao", "prompt", "modelo", "voz"]) f[k].value = p[k] || "";
  f.scrollIntoView({ behavior: "smooth" });
});
$("#form-persona").addEventListener("submit", async (e) => {
  e.preventDefault(); const f = e.target;
  await api("/api/personas", { method: "POST", json: Object.fromEntries(new FormData(f)) });
  f.reset(); carregarPersonas();
});

// ---------- Prompts ----------
async function carregarPrompts() {
  const d = await api("/api/prompts");
  const html = (lista, apagar) => lista.map((p) => `<div class="cartao item" data-texto="${esc(p.texto)}">
      ${apagar ? `<div class="acoes"><button class="icone" data-apagar-prompt="${p.id}">🗑️</button></div>` : ""}
      <small class="sutil">${esc(p.categoria)}</small><h3>${esc(p.titulo)}</h3><p>${esc(p.texto.slice(0, 140))}</p></div>`).join("");
  $("#lista-prompts").innerHTML = html(d.prompts, true);
  $("#modal-lista-prompts").innerHTML = d.prompts.map((p) => `<button data-texto="${esc(p.texto)}"><b>${esc(p.titulo)}</b><small>${esc(p.categoria)} · ${esc(p.texto.slice(0, 90))}</small></button>`).join("");
}
function usarPrompt(texto) { irPara("chat"); $("#modal-prompts").classList.add("oculto"); entrada.value = texto; ajustarEntrada(); entrada.focus(); }
$("#lista-prompts").addEventListener("click", async (e) => {
  const apagar = e.target.closest("[data-apagar-prompt]");
  if (apagar) { e.stopPropagation(); await api("/api/prompts/" + apagar.dataset.apagarPrompt, { method: "DELETE" }); return carregarPrompts(); }
  const item = e.target.closest("[data-texto]"); if (item) usarPrompt(item.dataset.texto);
});
$("#modal-lista-prompts").addEventListener("click", (e) => { const b = e.target.closest("[data-texto]"); if (b) usarPrompt(b.dataset.texto); });
$("#abrir-prompts").onclick = () => { carregarPrompts(); $("#modal-prompts").classList.remove("oculto"); };
$$("[data-fechar]").forEach((b) => (b.onclick = () => b.closest(".modal").classList.add("oculto")));
$("#form-prompt").addEventListener("submit", async (e) => {
  e.preventDefault(); await api("/api/prompts", { method: "POST", json: Object.fromEntries(new FormData(e.target)) }); e.target.reset(); carregarPrompts();
});

// ---------- Memória ----------
async function carregarMemoria() {
  const [f, l, c] = await Promise.all([api("/api/memoria"), api("/api/lembretes"), api("/api/conhecimento")]);
  $("#lista-fatos").innerHTML = f.fatos.map((x) => `<li><span>${esc(x.texto)}</span><button class="icone" data-fato="${x.id}">🗑️</button></li>`).join("") || '<li class="sutil">Nada guardado ainda. Diga "lembre que…".</li>';
  $("#lista-lembretes").innerHTML = l.lembretes.map((x) => `<li><span>${esc(x.texto)}<br><small class="sutil">${quando(x.quando)}${x.repetir_minutos ? " · repete a cada " + x.repetir_minutos + " min" : ""}</small></span><button class="icone" data-lembrete="${x.id}">🗑️</button></li>`).join("") || '<li class="sutil">Nenhum lembrete pendente.</li>';
  $("#lista-conhecimento").innerHTML = c.fontes.map((x) => `<li><span>📖 ${esc(x.titulo)}<br><small class="sutil">${esc(x.fonte)} · ${x.trechos} trechos</small></span><button class="icone" data-fonte="${esc(x.fonte)}">🗑️</button></li>`).join("") || '<li class="sutil">Nada estudado ainda.</li>';
}
$("#tela-memoria").addEventListener("click", async (e) => {
  const f = e.target.closest("[data-fato]"); const l = e.target.closest("[data-lembrete]"); const c = e.target.closest("[data-fonte]");
  if (f) await api("/api/memoria/" + f.dataset.fato, { method: "DELETE" });
  if (l) await api("/api/lembretes/" + l.dataset.lembrete, { method: "DELETE" });
  if (c) await api("/api/conhecimento?fonte=" + encodeURIComponent(c.dataset.fonte), { method: "DELETE" });
  if (f || l || c) carregarMemoria();
});
$("#form-fato").addEventListener("submit", async (e) => {
  e.preventDefault(); if (!e.target.texto.value.trim()) return;
  await api("/api/memoria", { method: "POST", json: { texto: e.target.texto.value } }); e.target.reset(); carregarMemoria();
});

// ---------- Ações ----------
async function carregarAcoes() {
  const d = await api("/api/acoes");
  $("#lista-acoes").innerHTML = d.acoes.map((a) => `<tr><td>${esc(a.quando)}</td><td><b>${esc(a.ferramenta)}</b></td><td><code>${esc(JSON.stringify(a.argumentos))}</code></td>
    <td><span class="nivel ${esc(a.nivel)}">${esc(a.nivel)}</span></td><td>${{ automatica: "✅ automática", aprovada: "👍 aprovada", negada: "❌ negada", bloqueada: "⛔ bloqueada" }[a.decisao] || esc(a.decisao)}</td></tr>`).join("")
    || '<tr><td colspan="5" class="sutil">Nenhuma ação ainda.</td></tr>';
}

// ---------- Casa ----------
async function carregarCasa() {
  const d = await api("/api/config");
  $("#casa-url").value = d.config.casa.url || ""; $("#casa-token").value = d.config.casa.token || "";
}
async function executarFerramenta(texto) { irPara("chat"); entrada.value = texto; enviar(); }
$("#casa-salvar").onclick = async () => {
  await api("/api/config", { method: "POST", json: { casa: { url: $("#casa-url").value.trim(), token: $("#casa-token").value.trim() } } });
  executarFerramenta("Liste os aparelhos da minha casa");
};
$("#casa-atualizar").onclick = () => executarFerramenta("Liste os aparelhos da minha casa e o estado de cada um");
$("#casa-bluetooth").onclick = () => executarFerramenta("Procure aparelhos Bluetooth por perto");
$("#casa-rede").onclick = () => executarFerramenta("Quais aparelhos estão conectados na rede da casa?");

// ---------- Configurações ----------
$$(".abas button").forEach((b) => (b.onclick = () => {
  $$(".abas button").forEach((x) => x.classList.toggle("ativo", x === b));
  $$(".painel").forEach((p) => p.classList.toggle("ativo", p.dataset.painel === b.dataset.aba));
}));
async function carregarConfig() {
  const [d, v] = await Promise.all([api("/api/config"), api("/api/vozes")]);
  estado.config = d.config; estado.vozes = v; estado.provedores = d.provedores;
  $("#config-caminho").textContent = "Arquivo: " + d.caminho;
  const f = $("#form-config");
  for (const el of f.elements) {
    if (!el.name || !el.name.includes(".")) continue;
    const [s, k] = el.name.split("."); const valor = (d.config[s] || {})[k];
    if (el.type === "checkbox") el.checked = !!valor; else el.value = valor ?? "";
  }
  const atual = d.config.voz.voz;
  $("#lista-vozes").innerHTML = v.vozes.map((x) => {
    const pronta = x.motor === "kokoro" ? v.kokoro : x.motor === "edge" ? v.edge : true;
    return `<div class="cartao voz ${x.id === atual || x.genero === atual && x.id === v.atual.id ? "ativa" : ""}">
      <h3>${x.genero === "feminina" ? "👩" : "👨"} ${esc(x.nome)}</h3><p class="sutil">${esc(x.descricao)}${pronta ? "" : " · não instalada"}</p>
      <div class="linha"><button type="button" class="botao" data-ouvir="${esc(x.id)}">▶ Ouvir</button><button type="button" class="botao primario" data-usar="${esc(x.id)}">Usar</button></div></div>`;
  }).join("");
  $$(".vozes-select").forEach((s) => (s.innerHTML = '<option value="">voz padrão</option>' + v.vozes.map((x) => `<option value="${esc(x.id)}">${esc(x.nome)} (${esc(x.descricao)})</option>`).join("")));
  desenharDestinos();
}
$("#lista-vozes").addEventListener("click", async (e) => {
  const ouvir = e.target.closest("[data-ouvir]"); const usar = e.target.closest("[data-usar]");
  if (ouvir) {
    const r = await api("/api/falar", { method: "POST", json: { texto: "Olá! Eu sou o Optimus, seu assistente pessoal. Como posso ajudar?", voz: ouvir.dataset.ouvir } });
    new Audio(URL.createObjectURL(await r.blob())).play();
  }
  if (usar) { await api("/api/config", { method: "POST", json: { voz: { voz: usar.dataset.usar } } }); carregarConfig(); }
});
function desenharDestinos() {
  const destinos = estado.config.destinos || [];
  const opcoes = ["ollama", ...Object.keys(estado.provedores || {})];
  $("#lista-destinos").innerHTML = destinos.map((d, i) => `<div class="destino" data-i="${i}"><div class="linha">
      <label>Nome<input class="campo" data-k="nome" value="${esc(d.nome || "")}"></label>
      <label>Tipo<select class="campo" data-k="backend">${opcoes.map((o) => `<option ${o === d.backend ? "selected" : ""}>${o}</option>`).join("")}</select></label>
      <label>Prioridade<input class="campo" type="number" data-k="prioridade" value="${d.prioridade ?? 5}"></label></div>
      <div class="linha"><label>Endereço<input class="campo" data-k="url" value="${esc(d.url || "")}" placeholder="http://192.168.0.20:11434 ou vazio para o padrão do provedor"></label>
      <label>Modelo<input class="campo" data-k="modelo" value="${esc(d.modelo || "")}"></label>
      <label>Chave de API<input class="campo" type="password" data-k="chave_api" value="${esc(d.chave_api || "")}"></label></div>
      <div class="linha"><label class="interruptor"><input type="checkbox" data-k="ativo" ${d.ativo !== false ? "checked" : ""}> Ativo</label><button type="button" class="botao" data-remover="${i}">Remover</button></div></div>`).join("")
    || '<p class="sutil">Nenhum destino extra. Só este PC está sendo usado.</p>';
}
function lerDestinos() {
  return $$("#lista-destinos .destino").map((el) => {
    const d = {};
    $$("[data-k]", el).forEach((c) => (d[c.dataset.k] = c.type === "checkbox" ? c.checked : c.type === "number" ? +c.value : c.value));
    return d;
  });
}
$("#novo-destino").onclick = () => { estado.config.destinos = [...lerDestinos(), { nome: "PC da sala", backend: "ollama", url: "http://192.168.0.20:11434", prioridade: 1, ativo: true }]; desenharDestinos(); };
$("#lista-destinos").addEventListener("click", (e) => {
  const r = e.target.closest("[data-remover]"); if (!r) return;
  const lista = lerDestinos(); lista.splice(+r.dataset.remover, 1); estado.config.destinos = lista; desenharDestinos();
});
$("#form-config").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dados = {};
  for (const el of e.target.elements) {
    if (!el.name || !el.name.includes(".")) continue;
    const [s, k] = el.name.split(".");
    dados[s] = dados[s] || {};
    dados[s][k] = el.type === "checkbox" ? el.checked : el.type === "number" ? (el.value === "" ? 0 : +el.value) : el.value;
  }
  dados.destinos = lerDestinos();
  await api("/api/config", { method: "POST", json: dados });
  $("#config-salvo").textContent = "✅ Salvo";
  setTimeout(() => ($("#config-salvo").textContent = ""), 2500);
  atualizarSistema();
});
$("#botao-baixar").onclick = async () => {
  const modelo = $("#modelo-baixar").value.trim(); if (!modelo) return;
  await api("/api/modelos/baixar", { method: "POST", json: { modelo } });
  const vigiar = setInterval(async () => {
    const p = (await api("/api/modelos/progresso"))[modelo] || {};
    $("#progresso-baixar").textContent = p.terminou ? (p.ok ? `✅ ${modelo} instalado` : `❌ Não consegui baixar ${modelo}. O Ollama está ligado?`) : `Baixando ${modelo}: ${p.pct || 0}% ${p.status || ""}`;
    if (p.terminou) { clearInterval(vigiar); atualizarSistema(); }
  }, 1000);
};

// ---------- Início ----------
async function iniciar() {
  await Promise.all([atualizarSistema(), carregarPersonas(), carregarConversas()]);
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}
iniciar();
setInterval(atualizarSistema, 4000);
