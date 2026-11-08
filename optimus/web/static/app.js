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
const aoVivo = { ligado: false, janelaAte: 0 };

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
  // Ao vivo, "pronto" quer dizer "ouvindo": o microfone continua aberto.
  if (tipo === "pronto" && aoVivo.ligado) { tipo = "ouvindo"; texto = texto === "Pronto" ? "Ouvindo… diga “Optimus”" : texto; }
  $("#orbe").className = "orbe " + tipo;
  $("#estado-texto").textContent = texto;
  Hud.estado(tipo);
}

// ---------- Navegação ----------
let modoHud = true;
try { modoHud = localStorage.getItem("optimus_hud") !== "0"; } catch (e) {}
function irPara(tela) {
  if (tela === "hud" || tela === "chat") {
    modoHud = tela === "hud";
    try { localStorage.setItem("optimus_hud", modoHud ? "1" : "0"); } catch (e) {}
    document.body.classList.toggle("modo-hud", modoHud);
    tela = "chat";
  }
  const ativo = tela === "chat" ? (modoHud ? "hud" : "chat") : tela;
  $$(".menu button").forEach((b) => b.classList.toggle("ativo", b.dataset.tela === ativo));
  $$("#hud-nav button").forEach((b) => b.classList.toggle("ativo", b.dataset.ir === (tela === "chat" ? "painel-conversa" : tela)));
  $$(".tela").forEach((t) => t.classList.toggle("ativa", t.id === "tela-" + tela));
  document.body.classList.toggle("fora-do-chat", tela !== "chat");
  app.classList.remove("lateral-aberta");
  const carregar = { personas: carregarPersonas, prompts: carregarPrompts, memoria: carregarMemoria, acoes: carregarAcoes, config: carregarConfig, casa: carregarCasa }[tela];
  if (carregar) carregar();
}
$$(".menu button").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.tela)));
$$("#hud-nav button").forEach((b) => b.addEventListener("click", () => {
  const destino = b.dataset.ir;
  if (destino === "painel-conversa") document.body.classList.toggle("transcricao-aberta");
  else irPara(destino);
}));
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
      Hud.anel("anel-" + id, valor / 100, Math.round(valor) + "%");
    }
    historicoCpu.push(d.uso.cpu); if (historicoCpu.length > 40) historicoCpu.shift();
    Hud.grafico($("#grafico-cpu"), historicoCpu);
    const aviso = $("#aviso-modelo");
    if (d.aviso_modelo && !aviso.dataset.mostrado) {
      aviso.dataset.mostrado = "1";
      aviso.innerHTML = "🧠 " + esc(d.aviso_modelo.texto) + `<div class="linha">${d.aviso_modelo.automatico ? "" : `<button class="botao pequeno primario" id="aceitar-modelo">Usar ${esc(d.aviso_modelo.modelo)}</button>`}<button class="botao pequeno" id="dispensar-modelo">${d.aviso_modelo.automatico ? "Entendi" : "Agora não"}</button></div>`;
      aviso.classList.remove("oculto");
    }
    else if (!d.aviso_modelo) aviso.classList.add("oculto");
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
const historicoCpu = [];
document.addEventListener("click", async (e) => {
  if (e.target.closest("#dispensar-modelo")) {
    try { await api("/api/modelo/dispensar", { method: "POST", json: {} }); } catch (err) {}
    $("#aviso-modelo").classList.add("oculto"); return;
  }
  if (!e.target.closest("#aceitar-modelo")) return;
  e.target.disabled = true;
  try { await api("/api/modelo/atualizar", { method: "POST", json: {} }); e.target.textContent = "Baixando… acompanhe em Configurações"; }
  catch (err) { e.target.textContent = "Falhou: " + err.message; }
});
const avisados = new Set();
function mostrarLembretes(avisos) {
  for (const a of avisos) {
    const chave = a.texto + a.quando;
    if (avisados.has(chave)) continue;
    avisados.add(chave);
    if (Date.now() / 1000 - a.quando > 60) continue;
    if ("Notification" in window && Notification.permission === "granted") new Notification("Optimus", { body: a.texto, icon: "/icone-192.png" });
    adicionarMensagem("optimus", `⏰ **Lembrete:** ${a.texto}`, { nome: "Lembrete" });
    if (estado.falar || aoVivo.ligado) falar("Lembrete: " + a.texto);
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
  if (ouvir) ouvir.onclick = () => Voz.falar(texto);
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
let tarefaAtual = "";
function legenda(quem, texto) {
  const el = $(quem === "usuario" ? "#legenda-usuario" : "#legenda-optimus");
  const t = String(texto || "").replace(/```[\s\S]*?```/g, " [código] ").replace(/[*#`>]/g, "").trim();
  el.textContent = t.length > 260 ? "…" + t.slice(-260) : t;
}

async function enviar(textoVoz) {
  const entrada = $("#entrada");
  const texto = (textoVoz || entrada.value).trim();
  if (!texto || estado.ocupado) return;
  entrada.value = ""; ajustarEntrada();
  estado.ocupado = true;
  $("#parar").classList.remove("oculto");
  adicionarMensagem("usuario", texto);
  legenda("usuario", texto); legenda("optimus", "");
  const resposta = adicionarMensagem("optimus", "", { persona: estado.persona });
  $(".texto", resposta).innerHTML = '<div class="digitando"><span></span><span></span><span></span></div>';
  definirEstado("pensando", "Pensando…");
  const grupo = estado.grupo ? $$("#grupo-escolha input:checked").map((i) => i.value) : null;
  const modo = estado.modo; desmarcarModo();
  try {
    const { tarefa } = await api("/api/enviar", { method: "POST", json: { conversa: estado.conversa, texto, persona: estado.persona, grupo: grupo && grupo.length ? grupo : null, voz: !!textoVoz, projeto: $("#filtro-projeto").value, modo } });
    tarefaAtual = tarefa;
    await acompanhar(tarefa, resposta, !!textoVoz);
  } catch (e) {
    if (e.message !== "senha") { $(".texto", resposta).innerHTML = `<p>⚠️ ${esc(e.message)}</p>`; legenda("optimus", "⚠️ " + e.message); }
  }
  tarefaAtual = "";
  estado.ocupado = false;
  $("#parar").classList.add("oculto");
  if (!Voz.falando()) definirEstado("pronto", "Pronto");
  carregarConversas();
}

$("#parar").onclick = async () => {
  Voz.parar();
  if (tarefaAtual) { try { await api("/api/cancelar", { method: "POST", json: { tarefa: tarefaAtual } }); } catch (e) {} }
  definirEstado("pronto", "Pronto");
};

function deveFalar(porVoz) { return estado.falar || aoVivo.ligado || porVoz; }

async function acompanhar(tarefa, bolha, porVoz) {
  let desde = 0; let pendenteId = ""; let atual = bolha; let usada = false;
  let parcial = ""; let falouParcial = false;
  const falar = deveFalar(porVoz);
  const novaBolha = () => { if (usada) { atual = adicionarMensagem("optimus", "", {}); usada = false; } };
  while (true) {
    let d;
    try { d = await api(`/api/tarefa/${tarefa}?desde=${desde}`); }
    catch (e) { if (e.message === "senha") return; await new Promise((r) => setTimeout(r, 1000)); continue; }
    desde = d.total;
    for (const ev of d.eventos) {
      if (ev.tipo === "conversa") estado.conversa = ev.id;
      else if (ev.tipo === "pensando") definirEstado("pensando", ev.passo > 1 ? `Pensando (passo ${ev.passo})…` : "Pensando…");
      else if (ev.tipo === "parcial") {
        novaBolha();
        parcial += ev.texto;
        $(".texto", atual).innerHTML = markdown(parcial);
        legenda("optimus", parcial);
        if (falar) { Voz.adicionarParcial(ev.texto); falouParcial = true; }
        else definirEstado("falando", "Respondendo…");
      } else if (ev.tipo === "limpar_parcial") {
        // O modelo começou a escrever e decidiu usar uma ferramenta: o texto era rascunho.
        parcial = ""; $(".texto", atual).innerHTML = '<div class="digitando"><span></span><span></span><span></span></div>';
        if (falouParcial) { Voz.parar(); falouParcial = false; }
      } else if (ev.tipo === "ferramenta") {
        novaBolha();
        definirEstado("executando", "Executando " + ev.nome);
        const passo = document.createElement("details");
        passo.className = "passo";
        passo.innerHTML = `<summary>🔧 <b>${esc(ev.nome)}</b> <span class="nivel ${esc(ev.nivel)}">${esc(ev.nivel)}</span> <span class="sutil">${esc(resumoArgs(ev.argumentos))}</span></summary><pre></pre>`;
        $(".passos", atual).appendChild(passo);
      } else if (ev.tipo === "resultado") {
        const passos = $$(".passo pre", atual);
        if (passos.length) passos[passos.length - 1].textContent = bonito(ev.resultado);
        mostrarMidia(ev.resultado, atual);
      } else if (ev.tipo === "negada" || ev.tipo === "aprovada") {
        const passos = $$(".passo summary", atual);
        if (passos.length) passos[passos.length - 1].insertAdjacentHTML("beforeend", ev.tipo === "negada" ? ' <span class="nivel bloqueado">negada</span>' : ' <span class="nivel livre">aprovada</span>');
      } else if (ev.tipo === "aviso") {
        $(".passos", atual).insertAdjacentHTML("beforeend", `<div class="passo">⚠️ ${esc(ev.texto)}</div>`);
      } else if (ev.tipo === "resposta" && ev.velocidade) {
        Hud.anel("anel-vel", Math.min(1, ev.velocidade / 40), String(Math.round(ev.velocidade)));
      } else if (ev.tipo === "final") {
        novaBolha(); usada = true;
        $(".texto", atual).innerHTML = markdown(ev.texto);
        legenda("optimus", ev.texto);
        $(".quem", atual).firstChild.textContent = ev.nome && ev.persona !== "optimus" ? ev.nome : estado.nome;
        $(".quem", atual).insertAdjacentHTML("beforeend", ` <span class="sutil">${ev.segundos}s</span>`);
        const [ouvir, copiar] = $$(".quem button", atual);
        ouvir.onclick = () => Voz.falar(ev.texto);
        copiar.onclick = () => navigator.clipboard && navigator.clipboard.writeText(ev.texto);
        if (falar) { if (falouParcial) Voz.finalizar(); else Voz.falar(ev.texto); }
        parcial = ""; falouParcial = false;
      } else if (ev.tipo === "erro") {
        $(".texto", atual).innerHTML = `<p>⚠️ ${esc(ev.texto)}</p>`;
        legenda("optimus", "⚠️ " + ev.texto);
        definirEstado("erro", "Erro");
      }
      $("#mensagens").scrollTop = $("#mensagens").scrollHeight;
    }
    if (d.pendente && d.pendente.id !== pendenteId) { pendenteId = d.pendente.id; mostrarConfirmacao(tarefa, d.pendente, atual); }
    if (!d.pendente && pendenteId) { $$(".confirmacao.aberta").forEach((c) => fecharConfirmacao(c, "")); pendenteId = ""; }
    if (d.terminou) break;
    await new Promise((r) => setTimeout(r, d.pendente ? 500 : 250));
  }
}
function resumoArgs(a) {
  const t = Object.entries(a || {}).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join(" · ");
  return t.length > 90 ? t.slice(0, 90) + "…" : t;
}
function bonito(t) { try { return JSON.stringify(JSON.parse(t), null, 2); } catch (e) { return t; } }
function mostrarMidia(resultado, bolha) {
  let dados; try { dados = JSON.parse(resultado); } catch (e) { return; }
  const imagens = [dados.imagem, ...(dados.imagens || [])].filter((x) => typeof x === "string" && x.startsWith("/api/midia/"));
  for (const src of imagens) {
    const fig = document.createElement("a"); fig.href = src; fig.target = "_blank"; fig.className = "midia";
    fig.innerHTML = `<img src="${esc(src)}" alt="Imagem gerada" loading="lazy">`;
    $(".passos", bolha).appendChild(fig);
  }
}

// ---------- Confirmações (Aprovar / Negar) ----------
let confirmacaoAberta = null;
function fecharConfirmacao(div, texto) {
  div.classList.remove("aberta");
  $$("button", div).forEach((b) => (b.disabled = true));
  if (texto) div.insertAdjacentHTML("beforeend", `<div class="sutil resultado-confirmacao">${texto}</div>`);
  if (confirmacaoAberta && confirmacaoAberta.div === div) confirmacaoAberta = null;
}
function mostrarConfirmacao(tarefa, p, bolha) {
  definirEstado("executando", "Aguardando sua confirmação");
  const critico = p.nivel >= 2;
  const div = document.createElement("div");
  div.className = "confirmacao aberta" + (critico ? " critico" : "");
  div.dataset.id = p.id;
  div.innerHTML = `<h4>${critico ? "⛔ Ação crítica" : "⚠️ Confirmar ação"}</h4>
    <div>O Optimus quer <b>${esc(p.motivo)}</b>.</div><code>${esc(p.nome)}(${esc(JSON.stringify(p.argumentos, null, 1))})</code>
    <div class="linha"><button type="button" class="botao aprovar" data-sim>✔ Aprovar</button><button type="button" class="botao negar" data-nao>✖ Negar</button></div>
    ${aoVivo.ligado ? `<div class="sutil">Ou diga ${critico ? "“confirmo”" : "“sim”"} ou “não”.</div>` : ""}`;
  $(".passos", bolha).appendChild(div);
  const responder = async (resposta) => {
    $$("button", div).forEach((b) => (b.disabled = true));
    try {
      const r = await api("/api/confirmar", { method: "POST", json: { tarefa, id: p.id, aprovar: resposta } });
      fecharConfirmacao(div, r.aprovado ? "✅ Aprovado por você" : "❌ Negado por você");
      definirEstado("pensando", r.aprovado ? "Executando…" : "Cancelado por você");
    } catch (e) {
      if (/respondida|pendente/.test(e.message)) fecharConfirmacao(div, "Esta confirmação já tinha sido respondida.");
      else { $$("button", div).forEach((b) => (b.disabled = false)); div.insertAdjacentHTML("beforeend", `<div class="sutil">⚠️ Não consegui enviar: ${esc(e.message)}. Tente de novo.</div>`); }
    }
  };
  $("[data-sim]", div).onclick = () => responder(true);
  $("[data-nao]", div).onclick = () => responder(false);
  confirmacaoAberta = { div, responder, critico };
  if (modoHud) document.body.classList.add("transcricao-aberta");
  if (deveFalar(false)) Voz.falar(`Atenção. Posso ${p.motivo}? ${critico ? "Diga confirmo para aprovar." : ""}`);
  div.scrollIntoView({ block: "nearest" });
}

// ---------- Entrada ----------
const entrada = $("#entrada");
function ajustarEntrada() { entrada.style.height = "auto"; entrada.style.height = Math.min(entrada.scrollHeight, 200) + "px"; }
entrada.addEventListener("input", ajustarEntrada);
entrada.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } });
$("#enviar").onclick = () => enviar();
const botaoFalar = $("#falar-respostas");
function desenharFalar() { botaoFalar.classList.toggle("ligado", estado.falar); botaoFalar.textContent = estado.falar ? "🔊" : "🔈"; }
botaoFalar.onclick = () => { estado.falar = !estado.falar; if (!estado.falar) Voz.parar(); try { localStorage.setItem("optimus_falar", estado.falar ? "1" : "0"); } catch (e) {} desenharFalar(); };
desenharFalar();
$("#persona").addEventListener("change", (e) => { estado.persona = e.target.value; if (estado.conversa) api("/api/conversas/" + estado.conversa, { method: "POST", json: { persona: estado.persona } }); });
$("#alternar-grupo").onclick = () => {
  estado.grupo = !estado.grupo;
  $("#alternar-grupo").classList.toggle("ligado", estado.grupo);
  $("#grupo-barra").classList.toggle("oculto", !estado.grupo);
};
// Modos: valem para o próximo pedido
estado.modo = "";
function desmarcarModo() { if (estado.modo !== "pensar" && estado.modo !== "programar") { estado.modo = ""; $$(".modos button").forEach((b) => b.classList.remove("ligado")); } }
$$(".modos button").forEach((b) => (b.onclick = () => {
  estado.modo = estado.modo === b.dataset.modo ? "" : b.dataset.modo;
  $$(".modos button").forEach((x) => x.classList.toggle("ligado", x.dataset.modo === estado.modo));
  entrada.placeholder = { web: "O que devo pesquisar na internet?", imagem: "Descreva a imagem…", pensar: "Pergunte algo difícil…", programar: "O que vamos programar?" }[estado.modo] || "Fale com o Optimus…";
  entrada.focus();
}));

// ---------- Voz ----------
Voz.config.api = api;
function falar(texto) { Voz.falar(texto); }

const PALAVRA = /\b(optimus|óptimus|optimos|ótimos|otimus|ótimus|optimu|op timus|opitimus|optmus)\b[,.!?]?\s*/i;
const PARE = /^(pare|para|parar|chega|silêncio|silencio|cala a boca|já chega|stop)\b/i;
function abrirJanela() { aoVivo.janelaAte = Date.now() + 25000; }
function avisoVoz(texto) { $("#rodape-voz").textContent = texto; }

Voz.ev.onNivel = (tipo, n) => Hud.nivel(n);
Voz.ev.onEstado = (s) => { if (s === "falando") definirEstado("falando", "Falando…"); };
Voz.ev.onFimFala = () => { if (!estado.ocupado) definirEstado("pronto", "Pronto"); if (aoVivo.ligado) abrirJanela(); };
Voz.ev.onErro = (m) => { avisoVoz("⚠️ " + m); };
Voz.ev.onPalmas = () => {
  // Palmas durante uma resposta não interrompem nada (som de fundo, música...).
  if (!aoVivo.ligado || estado.ocupado || Voz.falando()) return;
  abrirJanela(); legenda("usuario", "👏👏");
  Voz.falar(["Às ordens.", "Estou aqui.", "Pode falar."][Math.floor(Math.random() * 3)]);
};
Voz.ev.onTexto = (texto, final) => {
  if (!aoVivo.ligado && !gravandoManual) return;
  texto = String(texto || "").trim(); if (!texto) return;
  if (!final) { legenda("usuario", texto + "…"); return; }
  if (gravandoManual) return; // a gravação manual entrega o texto pela promessa
  tratarFalaAoVivo(texto);
};

function tratarFalaAoVivo(texto) {
  const temPalavra = PALAVRA.test(texto);
  const resto = texto.replace(PALAVRA, "").trim();
  // Interromper: "pare", "Optimus" ou "Optimus, pare" enquanto ele fala.
  if (Voz.falando()) {
    if (PARE.test(resto) || (temPalavra && !resto)) { Voz.parar(); abrirJanela(); definirEstado("pronto", "Pronto"); return; }
    if (!temPalavra) return; // provavelmente o eco da própria voz
    Voz.parar();
  }
  // Responder uma confirmação por voz
  if (confirmacaoAberta) {
    const t = resto || texto;
    if (/\b(sim|pode|confirmo|autorizo|aprovo|claro|ok|não|nao|negado|cancela)\b/i.test(t)) {
      legenda("usuario", t); confirmacaoAberta.responder(t); return;
    }
  }
  const naJanela = Date.now() < aoVivo.janelaAte;
  if (!temPalavra && !naJanela) { legenda("usuario", ""); return; }
  legenda("usuario", resto || texto);
  if (!resto) { abrirJanela(); Voz.falar(["Sim?", "Pois não?", "Estou ouvindo."][Math.floor(Math.random() * 3)]); return; }
  if (PARE.test(resto) && resto.split(/\s+/).length <= 2) { Voz.parar(); return; }
  if (estado.ocupado) { avisoVoz("Ainda estou respondendo o pedido anterior. Diga “Optimus, pare” para cancelar."); return; }
  abrirJanela();
  enviar(resto);
}

async function alternarAoVivo(ligar) {
  if (ligar === aoVivo.ligado) return;
  const botao = $("#botao-ao-vivo");
  if (ligar) {
    const ok = await Voz.iniciarEscuta();
    if (!ok) { avisoVoz("⚠️ Não consegui abrir o microfone. Libere o microfone para este site (cadeado na barra de endereço)."); return; }
    aoVivo.ligado = true; abrirJanela();
    botao.classList.add("ligado"); botao.textContent = "🔴 Ao vivo";
    avisoVoz(`Ao vivo: fale “Optimus…” ou bata duas palmas. Diga “pare” para interromper. Reconhecimento: ${Voz.modo === "navegador" ? "do navegador" : "Whisper no PC"}.`);
    definirEstado("pronto", "Pronto");
    Voz.falar("Modo ao vivo ligado. Pode falar.");
  } else {
    aoVivo.ligado = false; Voz.pararEscuta();
    botao.classList.remove("ligado"); botao.textContent = "🎙️ Ao vivo";
    avisoVoz("O Optimus executa ações no seu PC. Ações críticas sempre pedem sua confirmação.");
    definirEstado("pronto", "Pronto");
  }
  try { localStorage.setItem("optimus_ao_vivo", aoVivo.ligado ? "1" : "0"); } catch (e) {}
}
$("#botao-ao-vivo").onclick = () => alternarAoVivo(!aoVivo.ligado);
$("#hud-orbe").addEventListener("click", () => {
  if (Voz.falando()) { Voz.parar(); return; }
  if (aoVivo.ligado) { abrirJanela(); Voz.falar("Pode falar."); } else alternarAoVivo(true);
});

// Botão do microfone: um pedido falado (clique, fale, ele envia sozinho ao terminar).
let gravandoManual = false;
const mic = $("#microfone");
mic.addEventListener("click", async () => {
  if (gravandoManual) { if (Voz._pararGravacao) Voz._pararGravacao(); return; }
  Voz.parar();
  gravandoManual = true; mic.classList.add("gravando");
  definirEstado("ouvindo", "Ouvindo… fale agora");
  try {
    const texto = await Voz.gravarUmaVez(15);
    if (texto) enviar(texto); else definirEstado("pronto", "Não ouvi nada, tente de novo");
  } catch (e) {
    definirEstado("erro", "Reconhecimento de voz indisponível");
    avisoVoz("⚠️ " + (e.message === "not-allowed" ? "Microfone bloqueado: libere o microfone para este site." : e.message));
  }
  gravandoManual = false; mic.classList.remove("gravando");
});

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
let vigiaCameras = null;
async function carregarCasa() {
  const d = await api("/api/config");
  $("#casa-url").value = d.config.casa.url || ""; $("#casa-token").value = d.config.casa.token || "";
  try {
    const c = await api("/api/cameras");
    $("#cameras").innerHTML = c.cameras.map((x) => `<figure class="cartao camera"><img data-camera="${esc(x.id)}" alt="${esc(x.nome)}"><figcaption>${esc(x.nome)} <span class="sutil">ao vivo</span></figcaption></figure>`).join("")
      || '<p class="sutil">Nenhuma câmera encontrada ainda.</p>';
  } catch (e) { $("#cameras").innerHTML = `<p class="sutil">⚠️ ${esc(e.message)}</p>`; }
  clearInterval(vigiaCameras);
  const atualizar = () => {
    if (!$("#tela-casa").classList.contains("ativa")) { clearInterval(vigiaCameras); return; }
    $$("#cameras img[data-camera]").forEach(async (img) => {
      if (img.dataset.carregando) return;
      img.dataset.carregando = "1";
      try {
        const r = await api("/api/camera?id=" + encodeURIComponent(img.dataset.camera) + "&t=" + Date.now());
        const antigo = img.src; img.src = URL.createObjectURL(await r.blob());
        if (antigo.startsWith("blob:")) URL.revokeObjectURL(antigo);
        img.closest("figure").classList.remove("falhou");
      } catch (e) { img.closest("figure").classList.add("falhou"); }
      delete img.dataset.carregando;
    });
  };
  atualizar(); vigiaCameras = setInterval(atualizar, 1200);
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
  carregarFamilias();
}
async function carregarFamilias() {
  try {
    const d = await api("/api/modelos/catalogo");
    $("#familias-memoria").textContent = `Memória útil para o modelo: ${d.memoria_util_gb} GB (${d.gpu ? "placa de vídeo" : "RAM, sem placa de vídeo"}). Modelos de outras empresas também rodam pelo Ollama; para usar nuvem (OpenAI, Gemini, Grok, DeepSeek…), adicione em “Outras IAs e PCs”.`;
    $("#familias").innerHTML = d.familias.map((f) => `<div class="cartao familia"><h3>${esc(f.familia)}</h3>
      ${f.recomendado ? `<p><b>${esc(f.recomendado.nome)}</b> · ~${f.recomendado.memoria_gb} GB<br><span class="sutil">${esc(f.recomendado.descricao)}</span></p>
      <button type="button" class="botao pequeno" data-usar-modelo="${esc(f.recomendado.nome)}">Baixar e usar</button>` : '<p class="sutil">Nenhum modelo desta família cabe neste PC.</p>'}
      ${f.proximo ? `<p class="sutil">Próximo: ${esc(f.proximo.nome)} (~${f.proximo.memoria_gb} GB) não cabe ainda.</p>` : ""}</div>`).join("");
  } catch (e) { $("#familias").innerHTML = `<p class="sutil">⚠️ ${esc(e.message)}</p>`; }
}
$("#familias").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-usar-modelo]"); if (!b) return;
  const modelo = b.dataset.usarModelo;
  b.disabled = true; b.textContent = "Baixando…";
  await api("/api/config", { method: "POST", json: { motor: { modelo } } });
  $("#modelo-baixar").value = modelo; $("#botao-baixar").click();
  $("[name='motor.modelo']").value = modelo;
});
$("#lista-vozes").addEventListener("click", async (e) => {
  const ouvir = e.target.closest("[data-ouvir]"); const usar = e.target.closest("[data-usar]");
  if (ouvir) {
    try {
      const r = await api("/api/falar", { method: "POST", json: { texto: "Olá! Eu sou o Optimus, seu assistente pessoal. Como posso ajudar?", voz: ouvir.dataset.ouvir } });
      new Audio(URL.createObjectURL(await r.blob())).play();
    } catch (err) { ouvir.textContent = "⚠️ " + err.message.slice(0, 60); }
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
  Hud.iniciar($("#hud-orbe")); Hud.relogio();
  if (window.innerWidth <= 760) { entrada.placeholder = "Fale com o Optimus…"; $("#botao-ao-vivo").title = "Ao vivo"; } irPara(modoHud ? "hud" : "chat");
  Hud.boot();
  await Promise.all([atualizarSistema(), carregarPersonas(), carregarConversas()]);
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}
iniciar();
setInterval(atualizarSistema, 4000);
