/* Tela Estúdio de voz. Usa api(), esc(), $ e $$ do app.js. */
"use strict";

const Estudio = { vozes: [], idiomas: [], declaracao: "", vigia: null, carregado: false };
const EXT_MIDIA = /\.(mp3|wav|m4a|m4b|ogg|opus|flac|mp4|mkv|mov|webm)$/i;

async function estApi(caminho, opcoes) { return api("/api/estudio/" + caminho, opcoes || {}); }

function estAviso(onde, texto, erro) {
  const el = typeof onde === "string" ? $(onde) : onde;
  if (el) el.innerHTML = `<p class="${erro ? "erro" : "sutil"}">${esc(texto)}</p>`;
}

// Arquivos prontos: baixa com a senha no cabeçalho e mostra o player (ou o link).
async function estAbrir(caminho, alvo) {
  const r = await estApi("arquivo?caminho=" + encodeURIComponent(caminho));
  const url = URL.createObjectURL(await r.blob());
  const nome = caminho.split(/[\\/]/).pop();
  const caixa = document.createElement("div");
  caixa.className = "est-midia";
  if (/\.(mp4|mkv|mov|webm)$/i.test(nome)) caixa.innerHTML = `<video controls src="${url}"></video>`;
  else if (EXT_MIDIA.test(nome)) caixa.innerHTML = `<audio controls src="${url}"></audio>`;
  caixa.insertAdjacentHTML("beforeend", `<a class="botao" download="${esc(nome)}" href="${url}">⬇️ ${esc(nome)}</a>`);
  alvo.replaceChildren(caixa);
}

function estCaminhos(resultado) {
  const saida = [];
  const olhar = (v) => {
    if (typeof v === "string" && /[\\/]/.test(v) && /\.\w{2,4}$/.test(v)) saida.push(v);
    else if (Array.isArray(v)) v.forEach(olhar);
    else if (v && typeof v === "object") Object.values(v).forEach(olhar);
  };
  olhar(resultado);
  return [...new Set(saida)];
}

function estLinks(caminhos) {
  return caminhos.map((c) => `<button class="botao est-arquivo" data-caminho="${esc(c)}">▶ ${esc(c.split(/[\\/]/).pop())}</button>`).join(" ");
}

document.addEventListener("click", async (e) => {
  const b = e.target.closest(".est-arquivo");
  if (!b) return;
  let alvo = b.parentElement.querySelector(".est-player");
  if (!alvo) { alvo = document.createElement("div"); alvo.className = "est-player"; b.parentElement.appendChild(alvo); }
  try { await estAbrir(b.dataset.caminho, alvo); } catch (erro) { estAviso(alvo, erro.message, true); }
});

// Envia um arquivo escolhido (ou usa o caminho digitado). Devolve o caminho no PC.
async function estEntrada(campoArquivo, campoCaminho) {
  const arquivo = $(campoArquivo).files[0];
  if (arquivo) {
    // corpo cru (não formulário): o servidor grava direto no disco, até vídeos de 2 GB
    const r = await estApi("enviar", { method: "POST", body: arquivo,
      headers: { "Content-Type": "application/octet-stream", "X-Nome-Arquivo": encodeURIComponent(arquivo.name) } });
    return r.caminho;
  }
  const caminho = campoCaminho ? $(campoCaminho).value.trim() : "";
  if (!caminho) throw new Error("Escolha um arquivo ou cole o caminho dele.");
  return caminho;
}

// ---------- listas ----------
function estPreencherVozes() {
  const opcoes = Estudio.vozes.map((v) => `<option value="${esc(v.nome)}">${esc(v.nome)}${v.tipo !== "pronta" ? " (" + esc(v.tipo) + ")" : ""}</option>`).join("");
  const padrao = Estudio.vozes.some((v) => v.nome === "Valkyrie") ? "Valkyrie" : "";
  $$(".est-vozes").forEach((s) => { const atual = s.value; s.innerHTML = opcoes; s.value = atual || padrao || s.value; });
  $("#est-lista-vozes").innerHTML = Estudio.vozes.map((v) => `<tr><td><b>${esc(v.nome)}</b></td><td>${esc(v.tipo)}</td><td>${esc(v.descricao || "")}</td>
    <td>${v.tipo !== "pronta" ? `<button class="botao" data-apagar-voz="${esc(v.id)}">Apagar</button>` : ""}</td></tr>`).join("");
  $$(".est-declaracao").forEach((el) => { el.textContent = Estudio.declaracao; });
}

async function estCarregarVozes() {
  const r = await estApi("vozes");
  Estudio.vozes = r.vozes; Estudio.declaracao = r.declaracao;
  estPreencherVozes();
}

async function estCarregarIdiomas() {
  const r = await estApi("idiomas");
  Estudio.idiomas = r.idiomas;
  const opcoes = r.idiomas.map((i) => `<option value="${esc(i.codigo)}">${esc(i.nome)}</option>`).join("");
  $$(".est-idiomas").forEach((s) => { s.innerHTML = opcoes; s.value = "pt-BR"; });
}

const NOMES_ESTADO = { na_fila: "na fila", rodando: "rodando", concluida: "pronta", falhou: "falhou", cancelada: "cancelada", interrompida: "interrompida" };

async function estTarefas() {
  if (!$("#tela-estudio").classList.contains("ativa")) { clearInterval(Estudio.vigia); Estudio.vigia = null; return; }
  let r;
  try { r = await estApi("tarefas"); } catch (e) { return; }
  const caixa = $("#est-tarefas");
  if (!r.tarefas.length) { caixa.innerHTML = '<p class="sutil">Nenhuma tarefa ainda.</p>'; return; }
  caixa.innerHTML = r.tarefas.slice().reverse().map((t) => {
    const pct = Math.round((t.progresso || 0) * 100);
    const acoes = t.estado === "rodando" || t.estado === "na_fila"
      ? `<button class="botao" data-cancelar="${esc(t.id)}">Cancelar</button>`
      : (t.estado !== "concluida" ? `<button class="botao" data-repetir="${esc(t.id)}">Tentar de novo</button>` : "");
    return `<div class="est-tarefa"><div class="linha entre"><b>${esc(t.titulo)}</b><span class="sutil">${esc(NOMES_ESTADO[t.estado] || t.estado)} ${t.estado === "rodando" ? pct + "%" : ""}</span></div>
      <div class="est-barra"><span style="width:${t.estado === "concluida" ? 100 : pct}%"></span></div>
      <div class="sutil">${esc(t.erro || t.mensagem || "")}</div>
      <div class="linha">${t.estado === "concluida" ? estLinks(estCaminhos(t.resultado)) : ""} ${acoes}</div></div>`;
  }).join("");
}

function estVigiar() {
  estTarefas();
  if (!Estudio.vigia) Estudio.vigia = setInterval(estTarefas, 2500);
}

async function estHistorico() {
  const busca = $("#est-hist-busca").value.trim();
  const r = await estApi("historico?busca=" + encodeURIComponent(busca));
  $("#est-historico").innerHTML = r.itens.slice(0, 100).map((i) => `<tr><td class="sutil">${esc(i.quando)}</td><td>${esc(i.tipo)}</td>
    <td>${esc((i.texto || "").slice(0, 80))}</td><td>${esc(i.voz || "")}</td><td>${estLinks([i.arquivo])}</td>
    <td><button class="botao" data-favorito="${esc(i.id)}" title="Favorito">${i.favorito ? "★" : "☆"}</button>
    <button class="botao" data-apagar-hist="${esc(i.id)}" title="Apagar do histórico">🗑️</button></td></tr>`).join("") || '<tr><td class="sutil">Nada ainda.</td></tr>';
}

async function estPronuncia() {
  const r = await estApi("pronuncia");
  $("#est-pron-lista").innerHTML = r.regras.map((p) => `<tr><td><b>${esc(p.escrito)}</b></td><td>→ ${esc(p.falado)}</td>
    <td><button class="botao" data-remover-pron="${esc(p.escrito)}">Remover</button></td></tr>`).join("") || '<tr><td class="sutil">Nenhuma regra.</td></tr>';
}

async function estDiagnostico() {
  const r = await estApi("diagnostico");
  $("#est-diagnostico").innerHTML = r.itens.map((i) => `<li>${i.ok ? "✅" : "❌"} ${esc(i.nome)}${i.ok ? "" : ` <code>${esc(i.dica)}</code>`}</li>`).join("");
}

window.carregarEstudio = async function () {
  try {
    if (!Estudio.carregado) { await Promise.all([estCarregarVozes(), estCarregarIdiomas()]); Estudio.carregado = true; }
    else estCarregarVozes();
  } catch (e) { estAviso("#est-falar-saida", e.message, true); }
  estVigiar();
};

// ---------- abas ----------
$("#estudio-abas").addEventListener("click", (e) => {
  const b = e.target.closest("[data-aba-estudio]");
  if (!b) return;
  $$("#estudio-abas button").forEach((x) => x.classList.toggle("ativo", x === b));
  $$(".estudio-aba").forEach((a) => a.classList.toggle("oculto", a.dataset.aba !== b.dataset.abaEstudio));
  const extra = { historico: estHistorico, pronuncia: estPronuncia, ferramentas: estDiagnostico,
    modelos: estModelos, automacao: estReceitas }[b.dataset.abaEstudio];
  if (extra) extra().catch(() => {});
});

// ---------- ações ----------
async function estFila(rota, corpo, botao) {
  botao.disabled = true;
  try {
    const r = await estApi(rota, { method: "POST", json: corpo });
    estVigiar();
    return r;
  } finally { botao.disabled = false; }
}

$("#est-velocidade").addEventListener("input", (e) => { $("#est-vel-valor").textContent = Number(e.target.value).toFixed(2); });

$("#est-falar").addEventListener("click", async (e) => {
  const texto = $("#est-texto").value.trim();
  if (!texto) return estAviso("#est-falar-saida", "Escreva o texto primeiro.", true);
  estAviso("#est-falar-saida", "Gerando…");
  e.target.disabled = true;
  try {
    const r = await estApi("falar", { method: "POST", json: { texto, voz: $("#est-voz").value, idioma: $("#est-idioma").value, velocidade: Number($("#est-velocidade").value) } });
    await estAbrir(r.arquivo, $("#est-falar-saida"));
  } catch (erro) { estAviso("#est-falar-saida", erro.message, true); }
  finally { e.target.disabled = false; }
});

function estAtualizarVideo() {
  const dublar = $("#est-video-acao").value === "dublar";
  $$("#tela-estudio .so-dublar").forEach((el) => el.classList.toggle("oculto", !dublar));
  const original = dublar && $("#est-video-original").checked;
  $("#est-video-consent-linha").classList.toggle("oculto", !original);
  $("#est-video-voz").closest("label").classList.toggle("oculto", original);
}
$("#est-video-acao").addEventListener("change", estAtualizarVideo);
$("#est-video-original").addEventListener("change", estAtualizarVideo);

$("#est-video-ir").addEventListener("click", async (e) => {
  try {
    const arquivo = await estEntrada("#est-video-arquivo", "#est-video-caminho");
    const acao = $("#est-video-acao").value;
    const idioma = $("#est-video-idioma").value;
    const legenda = $("#est-video-legenda").value;
    if (acao === "legendar") {
      await estFila("legendar", { arquivo, idioma, no_video: legenda === "nenhuma" ? "nao" : legenda, falantes: $("#est-video-falantes").checked }, e.target);
    } else {
      const original = $("#est-video-original").checked;
      if (original && !$("#est-video-consent").checked) throw new Error("Para usar a voz de quem fala, marque a declaração de consentimento.");
      await estFila("dublar", { arquivo, idioma, voz: original ? "" : $("#est-video-voz").value, legenda, fundo: $("#est-video-fundo").value,
        separar_falantes: $("#est-video-falantes").checked, elenco: $("#est-video-elenco").value.trim(),
        voz_original: original, consentimento: $("#est-video-consent").checked }, e.target);
    }
  } catch (erro) { alert(erro.message); }
});

$("#est-criar").addEventListener("click", async (e) => {
  try {
    await estFila("criar-voz", { nome: $("#est-criar-nome").value.trim(), descricao: $("#est-criar-desc").value.trim(), motor: $("#est-criar-motor").value }, e.target);
    await estCarregarVozes();
  } catch (erro) { alert(erro.message); }
});

$("#est-clonar").addEventListener("click", async (e) => {
  const arquivo = $("#est-clonar-arquivo").files[0];
  if (!arquivo) return alert("Escolha a gravação da voz.");
  if (!$("#est-clonar-consent").checked) return alert("Marque a declaração de consentimento para clonar.");
  const dados = new FormData();
  dados.append("nome", $("#est-clonar-nome").value.trim());
  dados.append("consentimento", "true");
  dados.append("arquivo", arquivo, arquivo.name);
  e.target.disabled = true;
  try { await estApi("clonar", { method: "POST", body: dados }); await estCarregarVozes(); alert("Voz clonada."); }
  catch (erro) { alert(erro.message); }
  finally { e.target.disabled = false; }
});

$("#est-lista-vozes").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-apagar-voz]");
  if (!b) return;
  try { await estApi("vozes/" + encodeURIComponent(b.dataset.apagarVoz), { method: "DELETE" }); await estCarregarVozes(); }
  catch (erro) { alert(erro.message); }
});

$("#est-livro-ir").addEventListener("click", async (e) => {
  try {
    const arquivo = await estEntrada("#est-livro-arquivo", "#est-livro-caminho");
    const capa = $("#est-livro-capa").files[0] ? await estEntrada("#est-livro-capa") : "";
    await estFila("audiolivro", { arquivo, capa, voz: $("#est-livro-voz").value, titulo: $("#est-livro-titulo").value.trim(), autor: $("#est-livro-autor").value.trim() }, e.target);
  } catch (erro) { alert(erro.message); }
});

$("#est-hist-ir").addEventListener("click", async (e) => {
  const roteiro = $("#est-roteiro").value.trim();
  if (!roteiro) return alert("Escreva o roteiro.");
  try { await estFila("historia", { roteiro, elenco: $("#est-elenco").value.trim(), narrador: $("#est-narrador").value, titulo: $("#est-hist-titulo").value.trim() }, e.target); }
  catch (erro) { alert(erro.message); }
});

$$("[data-ferr]").forEach((b) => b.addEventListener("click", async () => {
  const saida = $("#est-ferr-saida");
  try {
    const arquivo = await estEntrada("#est-ferr-arquivo", "#est-ferr-caminho");
    estAviso(saida, "Trabalhando…");
    const corpo = { arquivo };
    if (b.dataset.ferr === "transcrever") corpo.formato = "srt";
    const r = await estFila(b.dataset.ferr, corpo, b);
    if (r.tarefa) return estAviso(saida, r.mensagem || "Comecei. Acompanhe em Tarefas.");
    if (b.dataset.ferr === "quem-fala") {
      saida.innerHTML = `<p><b>${r.pessoas}</b> pessoa(s): ${esc(Object.entries(r.tempo_de_fala).map(([k, v]) => k + " " + v).join(", "))}</p>`;
    } else if (b.dataset.ferr === "verificar") {
      saida.innerHTML = `<p>${r.marcado ? "✅" : "❔"} ${esc(r.resposta)} <span class="sutil">(pontuação ${r.pontuacao})</span></p>`;
    } else {
      saida.innerHTML = `<p class="sutil">${esc(r.mensagem || "Pronto.")}</p><div class="linha">${estLinks(estCaminhos(r))}</div>`;
    }
  } catch (erro) { estAviso(saida, erro.message, true); }
}));

$("#est-pron-add").addEventListener("click", async () => {
  try { await estApi("pronuncia", { method: "POST", json: { escrito: $("#est-pron-escrito").value.trim(), falado: $("#est-pron-falado").value.trim() } }); $("#est-pron-escrito").value = ""; $("#est-pron-falado").value = ""; estPronuncia(); }
  catch (erro) { alert(erro.message); }
});
$("#est-pron-lista").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-remover-pron]");
  if (b) { await estApi("pronuncia/" + encodeURIComponent(b.dataset.removerPron), { method: "DELETE" }); estPronuncia(); }
});

$("#est-hist-busca").addEventListener("input", () => { clearTimeout(Estudio.buscaRelogio); Estudio.buscaRelogio = setTimeout(estHistorico, 300); });
$("#est-historico").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-favorito]");
  if (b) { await estApi(`historico/${encodeURIComponent(b.dataset.favorito)}/favorito`, { method: "POST" }); estHistorico(); }
  const a = e.target.closest("[data-apagar-hist]");
  if (a) {
    const arq = $("#est-hist-arquivos").checked ? "?arquivos=1" : "";
    await estApi(`historico/${encodeURIComponent(a.dataset.apagarHist)}${arq}`, { method: "DELETE" });
    estHistorico();
  }
});
$("#est-hist-limpar").addEventListener("click", async () => {
  const arquivos = $("#est-hist-arquivos").checked;
  const aviso = "Apagar todo o histórico do Estúdio? Os favoritos (★) ficam."
    + (arquivos ? " Os arquivos de áudio e vídeo gerados também serão apagados." : "");
  if (!confirm(aviso)) return;
  await estApi("historico" + (arquivos ? "?arquivos=1" : ""), { method: "DELETE" });
  estHistorico();
});

$("#est-tarefas").addEventListener("click", async (e) => {
  const c = e.target.closest("[data-cancelar]"), r = e.target.closest("[data-repetir]");
  if (c) await estApi(`tarefas/${encodeURIComponent(c.dataset.cancelar)}/cancelar`, { method: "POST" });
  if (r) await estApi(`tarefas/${encodeURIComponent(r.dataset.repetir)}/repetir`, { method: "POST" });
  if (c || r) estTarefas();
});

// ---------- modelos e desempenho ----------
const NOMES_TIPO = { voz: "voz", clonagem: "clonagem", transcricao: "transcrição", isolamento: "separar voz", falantes: "quem fala" };

async function estModelos() {
  const r = await estApi("modelos");
  $("#est-desempenho").value = r.desempenho || "auto";
  $("#est-desempenho-info").textContent = `Agora: ${r.atual.descricao} (transcrição ${r.atual.transcricao}). Recomendado para este PC: ${r.recomendada}. Python do Optimus: ${r.python || "?"} (instale os motores nele; um pip solto pode ir para outro Python).`;
  $("#est-modelos").innerHTML = r.modelos.map((m) => `<tr><td>${m.instalado ? "✅" : ""}</td>
    <td><b>${esc(m.nome)}</b><div class="sutil">${esc(m.descricao)}</div>${!m.instalado && m.comando ? `<div class="sutil">À mão: <code>${esc(m.comando)}</code></div>` : ""}</td><td>${esc(NOMES_TIPO[m.tipo] || m.tipo)}</td>
    <td>${esc(m.licenca)}</td><td>${m.ocupado_mb ? esc(m.ocupado_mb + " MB") : "~" + esc(m.tamanho_mb) + " MB"}</td>
    <td>${m.instalado ? `<button class="botao" data-modelo-remover="${esc(m.id)}">Remover</button>` : `<button class="botao primario" data-modelo-instalar="${esc(m.id)}">Instalar</button>`}</td></tr>`).join("");
}

$("#est-desempenho").addEventListener("change", async (e) => {
  try { await estApi("desempenho", { method: "POST", json: { escolha: e.target.value } }); estModelos(); }
  catch (erro) { alert(erro.message); }
});

$("#est-modelos-instalar-todos").addEventListener("click", async (e) => {
  const botao = e.currentTarget;
  if (!confirm("Isso pode baixar vários gigabytes e ocupar bastante espaço. Deseja instalar todos os motores e modelos?")) return;
  botao.disabled = true; botao.textContent = "⏳ Preparando downloads…";
  try {
    const r = await estApi("modelos/instalar-todos", { method: "POST" });
    estAviso("#est-desempenho-info", r.mensagem || "Instalação adicionada à fila. Acompanhe em Tarefas.");
    estVigiar();
  } catch (erro) { alert(erro.message); }
  finally { botao.disabled = false; botao.textContent = "⬇ Baixar e integrar todos"; }
});

$("#est-modelos").addEventListener("click", async (e) => {
  const i = e.target.closest("[data-modelo-instalar]"), r = e.target.closest("[data-modelo-remover]");
  if (!i && !r) return;
  const botao = i || r;
  const id = i ? i.dataset.modeloInstalar : r.dataset.modeloRemover;
  if (r && !confirm("Remover " + id + "?")) return;
  botao.disabled = true;
  try {
    const resp = await estApi(`modelos/${encodeURIComponent(id)}/${i ? "instalar" : "remover"}`, { method: "POST" });
    if (!i) return estModelos();
    const idTarefa = resp && resp.tarefa;
    botao.textContent = "Instalando…"; estVigiar();
    // A instalação roda em Tarefas; a lista se atualiza sozinha quando ela termina.
    let voltas = 0;
    const vigia = setInterval(async () => {
      voltas++;
      try {
        const lista = (await estApi("modelos")).modelos;
        const item = lista.find((m) => m.id === id);
        const tarefas = (await estApi("tarefas")).tarefas || [];
        const minha = tarefas.find((t) => t.id === idTarefa);
        const rodando = minha ? (minha.estado === "rodando" || minha.estado === "na_fila") : voltas < 3;
        if (minha && minha.estado === "falhou") {
          clearInterval(vigia); await estModelos();
          return estAviso($("#est-desempenho-info"), "Não instalou " + id + ": " + (minha.erro || "veja em Tarefas"), true);
        }
        if ((item && item.instalado) || !rodando || voltas > 600) { clearInterval(vigia); estModelos(); }
      } catch (erro) { clearInterval(vigia); estModelos(); }
    }, 3000);
  } catch (erro) { alert(erro.message); botao.disabled = false; }
});

// ---------- receitas e pastas observadas ----------
async function estReceitas() {
  const r = await estApi("receitas");
  const nomes = r.receitas.map((x) => `<option value="${esc(x.nome)}">${esc(x.nome)}</option>`).join("");
  document.querySelectorAll(".est-receitas").forEach((s) => { const atual = s.value; s.innerHTML = nomes; if (atual) s.value = atual; });
  if (!$("#est-rec-acao").options.length) {
    $("#est-rec-acao").innerHTML = r.acoes.map((a) => `<option value="${esc(a)}">${esc(a.replace("estudio_", "").replace(/_/g, " "))}</option>`).join("");
  }
  $("#est-rec-lista").innerHTML = r.receitas.map((x) => `<tr><td><b>${esc(x.nome)}</b><div class="sutil">${esc(x.descricao || "")}</div></td>
    <td>${esc(x.acao.replace("estudio_", ""))}</td><td class="sutil">${esc(Object.entries(x.opcoes).map(([k, v]) => k + "=" + v).join("; "))}</td>
    <td>${x.pronta ? "" : `<button class="botao" data-receita-apagar="${esc(x.nome)}">Apagar</button>`}</td></tr>`).join("");
  $("#est-obs-lista").innerHTML = r.observadas.map((o) => `<tr><td>📂 ${esc(o.pasta)}</td><td>→ ${esc(o.receita)}</td>
    <td><button class="botao" data-obs-parar="${esc(o.pasta)}">Parar</button></td></tr>`).join("") || '<tr><td class="sutil">Nenhuma pasta observada.</td></tr>';
}

$("#est-rec-salvar").addEventListener("click", async (e) => {
  try {
    await estFila("receitas", { nome: $("#est-rec-nome").value.trim(), acao: $("#est-rec-acao").value, opcoes: $("#est-rec-opcoes").value.trim() }, e.target);
    $("#est-rec-nome").value = ""; $("#est-rec-opcoes").value = ""; estReceitas();
  } catch (erro) { alert(erro.message); }
});

$("#est-obs-ir").addEventListener("click", async (e) => {
  try { await estFila("observar", { pasta: $("#est-obs-pasta").value.trim(), receita: $("#est-obs-receita").value }, e.target); estReceitas(); }
  catch (erro) { alert(erro.message); }
});

$("#est-rec-rodar").addEventListener("click", async (e) => {
  const saida = $("#est-rec-saida");
  try {
    const arquivo = await estEntrada("#est-rec-arquivo", "#est-rec-caminho");
    const r = await estFila(`receitas/${encodeURIComponent($("#est-rec-rodar-nome").value)}/rodar`, { arquivo }, e.target);
    if (r.tarefa) estAviso(saida, r.mensagem || "Comecei. Acompanhe em Tarefas.");
    else saida.innerHTML = `<p class="sutil">${esc(r.mensagem || "Pronto.")}</p><div class="linha">${estLinks(estCaminhos(r))}</div>`;
  } catch (erro) { estAviso(saida, erro.message, true); }
});

$("#est-rec-lista").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-receita-apagar]");
  if (b) { await estApi("receitas/" + encodeURIComponent(b.dataset.receitaApagar), { method: "DELETE" }); estReceitas(); }
});
$("#est-obs-lista").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-obs-parar]");
  if (b) { await estApi("observar?pasta=" + encodeURIComponent(b.dataset.obsParar), { method: "DELETE" }); estReceitas(); }
});

estAtualizarVideo();
