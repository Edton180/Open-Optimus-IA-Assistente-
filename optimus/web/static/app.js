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
  const { tempo = 12000, json, ...fetchOpcoes } = opcoes;
  const cab = Object.assign({}, fetchOpcoes.headers || {});
  if (senha) cab["X-Optimus-Senha"] = senha;
  if (json !== undefined) { cab["Content-Type"] = "application/json"; fetchOpcoes.body = JSON.stringify(json); }
  // O prazo cobre conexão E leitura do corpo. Sem prazo, uma resposta parcial podia
  // deixar o status inicial preso em "carregando…" indefinidamente.
  const controle = new AbortController();
  const relogio = tempo > 0 ? setTimeout(() => controle.abort(), tempo) : null;
  try {
    const r = await fetch(caminho, { ...fetchOpcoes, headers: cab, signal: controle.signal });
    if (r.status === 401) { pedirSenha(); throw new Error("senha"); }
    const tipo = r.headers.get("Content-Type") || "";
    if (tipo.includes("json")) {
      const dados = await r.json();
      if (!r.ok) throw new Error(dados.erro || r.statusText);
      return dados;
    }
    if (!r.ok) throw new Error(r.statusText || ("HTTP " + r.status));
    return r;
  } catch (erro) {
    if (erro && erro.name === "AbortError") throw new Error("Tempo esgotado ao acessar " + caminho + ". Verifique se o servidor do Optimus está respondendo.");
    throw erro;
  } finally {
    if (relogio) clearTimeout(relogio);
  }
}

function pedirSenha() {
  $("#modal-senha").classList.remove("oculto");
  const campo = $("#form-senha")?.elements.namedItem("senha");
  if (campo) { campo.focus(); campo.setAttribute("autocomplete", "current-password"); }
}
$("#form-senha").addEventListener("submit", async (e) => {
  e.preventDefault();
  const formulario = e.currentTarget;
  const campo = formulario.elements.namedItem("senha");
  const botao = formulario.querySelector("button[type=submit], button");
  const valor = String(campo?.value || "");
  if (!valor) { if (campo) campo.placeholder = "Digite a senha configurada no PC"; return; }
  if (botao) { botao.disabled = true; botao.textContent = "Verificando…"; }
  try {
    const resposta = await fetch("/api/entrar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ senha: valor }),
      cache: "no-store",
    });
    if (!resposta.ok) {
      senha = "";
      try { sessionStorage.removeItem("optimus_senha"); } catch (err) {}
      if (campo) { campo.value = ""; campo.placeholder = resposta.status === 401 ? "Senha incorreta — tente novamente" : "Não foi possível validar a senha"; campo.focus(); }
      return;
    }
    senha = valor;
    try { sessionStorage.setItem("optimus_senha", senha); } catch (err) {}
    $("#modal-senha").classList.add("oculto");
    await iniciar();
  } catch (erro) {
    console.error("Falha ao validar a senha do Optimus:", erro);
    if (campo) { campo.placeholder = "Servidor indisponível — tente novamente"; campo.focus(); }
  } finally {
    if (botao) { botao.disabled = false; botao.textContent = "Entrar"; }
  }
});

// ---------- Utilidades ----------
function esc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function markdown(texto) {
  const blocos = [];
  let t = String(texto || "").replace(/\x60{3}([\w-]*)\r?\n?([\s\S]*?)\x60{3}/g, (_, linguagem, conteudo) => {
    const marcador = "@@OPTIMUS_CODE_" + blocos.length + "@@";
    blocos.push(conteudo);
    return "\n" + marcador + "\n";
  });
  t = esc(t)
    .replace(/\x60([^\x60]+)\x60/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>')
    .replace(/^#{1,4} (.+)$/gm, "<strong>$1</strong>");
  const linhas = t.split(/\r?\n/);
  let html = "";
  let lista = null;
  for (const linha of linhas) {
    const item = linha.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)/);
    if (item) {
      const tipo = item[1] ? "ol" : "ul";
      if (lista !== tipo) {
        if (lista) html += "</" + lista + ">";
        html += "<" + tipo + ">";
        lista = tipo;
      }
      html += "<li>" + item[2] + "</li>";
      continue;
    }
    if (lista) { html += "</" + lista + ">"; lista = null; }
    if (linha.trim()) html += "<p>" + linha + "</p>";
  }
  if (lista) html += "</" + lista + ">";
  return html.replace(/@@OPTIMUS_CODE_(\d+)@@/g, (_, indice) =>
    "<pre><code>" + esc(blocos[Number(indice)] || "") + "</code></pre>");
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
  const carregar = { zim: carregarZim, personas: carregarPersonas, prompts: carregarPrompts, memoria: carregarMemoria, biblioteca: carregarBiblioteca, acoes: carregarAcoes, config: carregarConfig, casa: carregarCasa, estudio: () => window.carregarEstudio && window.carregarEstudio(), pdf: carregarPDF, modulos: carregarModulos, laboratorio: () => {} }[tela];
  if (carregar) carregar();
}

// ---------- Biblioteca local ZIM ----------
async function carregarZim() {
  const status = $("#zim-status");
  const lista = $("#zim-lista");
  const resumo = $("#zim-resumo");
  if (!status || !lista || !resumo) return;
  status.textContent = "Consultando arquivos ZIM locais…";
  try {
    const dados = await api("/api/zim");
    const arquivos = Array.isArray(dados.arquivos) ? dados.arquivos : [];
    resumo.innerHTML = [
      ["Arquivos", String(dados.total ?? arquivos.length)],
      ["Espaço ocupado", formatarBytes(dados.tamanho_total_bytes ?? 0)]
    ].map(([nome, valor]) => '<article class="cartao"><small class="sutil">' + esc(nome) +
      '</small><h3>' + esc(valor) + '</h3></article>').join("");
    lista.innerHTML = arquivos.length ? arquivos.map((arquivo) =>
      '<li><div><b>' + esc(arquivo.nome) + '</b><small class="sutil"> ' +
      esc(formatarBytes(arquivo.tamanho_bytes)) + ' · modificado em ' +
      esc(quando(arquivo.modificado_em)) + '</small></div></li>'
    ).join("") : '<li class="sutil">Nenhum arquivo ZIM encontrado. Adicione arquivos à pasta biblioteca_zim.</li>';
    status.textContent = dados.pasta_configurada === false
      ? "Não foi possível acessar a pasta da biblioteca: " + (dados.erro || "erro desconhecido")
      : "Catálogo atualizado · " + new Date().toLocaleTimeString("pt-BR");
    const seletor = $("#zim-arquivo");
    if (seletor) {
      const selecionado = seletor.value;
      seletor.innerHTML = '<option value="">Selecione um arquivo ZIM</option>' +
        arquivos.map((a) => '<option value="' + esc(a.nome) + '">' + esc(a.nome) + ' (' +
          esc(formatarBytes(a.tamanho_bytes)) + ')</option>').join("");
      if (arquivos.some((a) => a.nome === selecionado)) seletor.value = selecionado;
      $("#zim-abrir").disabled = !seletor.value || !dados.kiwix?.instalado || !!dados.kiwix?.executando;
    }
    atualizarEstadoKiwix(dados.kiwix || {});
  } catch (erro) {
    status.textContent = "Falha ao consultar a biblioteca: " + erro.message;
    lista.innerHTML = "";
    resumo.innerHTML = "";
  }
}
function atualizarEstadoKiwix(dados) {
  const badge = $("#zim-kiwix-status");
  const status = $("#zim-leitor-status");
  const link = $("#zim-leitor-link");
  if (!badge || !status || !link) return;
  badge.textContent = dados.executando ? "Leitor em execução" :
    dados.instalado ? "Kiwix instalado" : "Kiwix não instalado";
  status.textContent = dados.executando
    ? "Leitura ativa: " + (dados.arquivo || "arquivo ZIM") + ". O servidor está disponível somente neste computador."
    : dados.instalado ? "Pronto para iniciar sob demanda." :
      "Instale kiwix-tools no sistema para habilitar a leitura. Nenhum serviço foi iniciado.";
  link.innerHTML = dados.executando && dados.url
    ? '<a href="' + esc(dados.url) + '" target="_blank" rel="noopener noreferrer">Abrir leitor Kiwix em nova aba ↗</a>'
    : "";
  $("#zim-fechar").disabled = !dados.executando;
  $("#zim-abrir").disabled = !dados.instalado || !!dados.executando || !$("#zim-arquivo")?.value;
  if (dados.executando && $("#zim-arquivo")) $("#zim-arquivo").value = dados.arquivo || "";
}
$("#zim-atualizar")?.addEventListener("click", carregarZim);
$("#zim-arquivo")?.addEventListener("change", () => {
  const badge = $("#zim-kiwix-status");
  $("#zim-abrir").disabled = !$("#zim-arquivo").value ||
    badge?.textContent === "Kiwix não instalado" ||
    badge?.textContent === "Leitor em execução";
});
$("#zim-abrir")?.addEventListener("click", async () => {
  const botao = $("#zim-abrir");
  const status = $("#zim-leitor-status");
  const arquivo = $("#zim-arquivo")?.value;
  if (!arquivo) return;
  botao.disabled = true;
  status.textContent = "Iniciando leitor local…";
  try {
    const dados = await api("/api/zim/iniciar", { method: "POST", json: { arquivo }, tempo: 15000 });
    atualizarEstadoKiwix(dados);
  } catch (erro) {
    status.textContent = "Não foi possível iniciar o leitor: " + erro.message;
    botao.disabled = false;
  }
});
$("#zim-fechar")?.addEventListener("click", async () => {
  const botao = $("#zim-fechar");
  botao.disabled = true;
  $("#zim-leitor-status").textContent = "Encerrando o leitor iniciado pelo Optimus…";
  try {
    const dados = await api("/api/zim/parar", { method: "POST", json: {} });
    atualizarEstadoKiwix(dados);
  } catch (erro) {
    $("#zim-leitor-status").textContent = "Falha ao encerrar o leitor: " + erro.message;
    botao.disabled = false;
  }
});

// ---------- Command Center: inventário local de integrações ----------
async function carregarModulos() {
  const estadoEl = $("#modulos-estado");
  const grade = $("#modulos-grade");
  if (!estadoEl || !grade) return;
  estadoEl.textContent = "Verificando executáveis e serviços locais…";
  try {
    const [dados, telemetria] = await Promise.all([
      api("/api/modulos"), api("/api/modulos/recursos")
    ]);
    desenharRecursosModulos(telemetria.recursos || {});
    const itens = dados.modulos || [];
    grade.innerHTML = itens.map((m) => {
      const status = m.estado === "disponivel" ? "Disponível" :
        m.estado === "instalado_parado" ? "Instalado · serviço indisponível" :
        m.estado === "nativo" ? "Recurso nativo do Optimus" : "Não instalado";
      return `<article class="cartao"><div class="linha entre"><b>${esc(m.nome)}</b><span class="selo">${esc(status)}</span></div>
        <p>${esc(m.descricao)}</p><small class="sutil">${esc(m.detalhe || "Detecção local")}</small></article>`;
    }).join("") || '<p class="sutil">Nenhum módulo foi identificado.</p>';
    estadoEl.textContent = `${itens.length} componentes verificados · ${new Date().toLocaleTimeString("pt-BR")}`;
  } catch (erro) {
    estadoEl.textContent = "Não foi possível consultar o inventário: " + erro.message;
  }
}
function formatarBytes(valor) {
  if (valor == null) return "Indisponível";
  const unidades = ["B", "KB", "MB", "GB", "TB"];
  let n = Number(valor), i = 0;
  while (n >= 1024 && i < unidades.length - 1) { n /= 1024; i++; }
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " " + unidades[i];
}
function desenharRecursosModulos(r) {
  const alvo = $("#modulos-recursos");
  if (!alvo) return;
  const memoriaUsada = Math.max(0, (r.memoria_total_bytes || 0) - (r.memoria_disponivel_bytes || 0));
  const discoUsado = Math.max(0, (r.disco_total_bytes || 0) - (r.disco_livre_bytes || 0));
  const cards = [
    ["Processador", (r.cpu_percentual ?? 0) + "% em uso", (r.cpu_nucleos_fisicos ?? "—") + " núcleos físicos · " + (r.cpu_nucleos_logicos ?? "—") + " lógicos"],
    ["Memória RAM", formatarBytes(memoriaUsada) + " / " + formatarBytes(r.memoria_total_bytes), (r.memoria_percentual ?? "—") + "% utilizada"],
    ["Armazenamento", formatarBytes(discoUsado) + " / " + formatarBytes(r.disco_total_bytes), (r.disco_percentual ?? "—") + "% utilizado"],
    ["Sistema", (r.processos ?? "—") + " processos", "Ligado há " + Math.floor((r.uptime_segundos || 0) / 3600) + " horas"]
  ];
  alvo.innerHTML = cards.map(([titulo, valor, detalhe]) =>
    '<article class="cartao"><b>' + esc(titulo) + '</b><h3>' + esc(valor) + '</h3><small class="sutil">' + esc(detalhe) + '</small></article>'
  ).join("");
  const atualizado = $("#modulos-recursos-atualizado");
  if (atualizado) atualizado.textContent = "Atualizado às " + new Date().toLocaleTimeString("pt-BR");
}
$("#modulos-atualizar")?.addEventListener("click", carregarModulos);
$("#lab-executar")?.addEventListener("click", async () => {
  const estadoEl = $("#lab-estado");
  const botao = $("#lab-executar");
  const resultado = $("#lab-resultado");
  if (!estadoEl || !botao || !resultado) return;
  estadoEl.textContent = "Processando localmente…";
  botao.disabled = true;
  $("#lab-copiar").disabled = true;
  try {
    const dados = await api("/api/laboratorio", {
      method: "POST", json: {
        operacao: $("#lab-operacao").value,
        texto: $("#lab-entrada").value
      }
    });
    resultado.value = dados.resultado ?? "";
    estadoEl.textContent = "Concluído neste computador.";
    $("#lab-copiar").disabled = false;
  } catch (erro) {
    resultado.value = "";
    estadoEl.textContent = "Falha: " + erro.message;
  } finally { botao.disabled = false; }
});
$("#lab-limpar")?.addEventListener("click", () => {
  $("#lab-entrada").value = "";
  $("#lab-resultado").value = "";
  $("#lab-estado").textContent = "";
  $("#lab-copiar").disabled = true;
});
$("#lab-copiar")?.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("#lab-resultado").value);
    $("#lab-estado").textContent = "Resultado copiado.";
  } catch (erro) { $("#lab-estado").textContent = "Não foi possível copiar: " + erro.message; }
});

// ---------- Central visual de documentos e PDF ----------
let pdfFerramentas = [];
let pdfEnviados = [];
let pdfCategoriaAtiva = "Todas";
const PDF_CATEGORIAS = ["Todas", "Criar e converter", "Organizar páginas", "Editar e anotar",
  "Otimizar e reparar", "Segurança e privacidade", "Verificar e analisar", "Formulários e assinatura"];
const PDF_ROTULOS = {
  pdf_info:"Informações do PDF", pdf_ler:"Extrair texto", pdf_juntar:"Unir PDFs",
  pdf_unir_documentos:"Unir PDFs, imagens e Office", pdf_documento_para_pdf:"Word, Excel e PowerPoint para PDF",
  pdf_dividir_pares_impares:"Separar páginas pares e ímpares", pdf_paginas_por_folha:"Várias páginas por folha",
  pdf_imprimir_livreto:"Preparar impressão em livreto",
  pdf_extrair:"Extrair páginas", pdf_remover:"Eliminar páginas", pdf_organizar:"Ordenar páginas",
  pdf_dividir:"Dividir PDF", pdf_girar:"Girar páginas", pdf_proteger:"Proteger com senha",
  pdf_desbloquear:"Desbloquear PDF", pdf_comprimir:"Comprimir PDF", pdf_marca:"Adicionar marca d'água",
  pdf_numeros:"Adicionar números de página", pdf_assinar:"Inserir assinatura visual",
  pdf_localizar_termos:"Buscar texto sensível", pdf_censurar:"Censurar conteúdo",
  pdf_comparar:"Comparar textos", pdf_ocr:"OCR de documentos escaneados",
  pdf_converter:"Converter PDF", pdf_resumir:"Resumir documento",
  pdf_imagens_para_pdf:"Imagens para PDF", pdf_para_imagens:"PDF para imagens",
  pdf_cortar:"Recortar páginas", pdf_metadados:"Editar metadados", pdf_reparar:"Reparar PDF",
  pdf_para_markdown:"PDF para Markdown", pdf_html_para_pdf:"HTML para PDF",
  pdf_formularios:"Ler e preencher formulários", pdf_para_excel:"PDF para Excel",
  pdf_para_powerpoint:"PDF para PowerPoint", pdf_comparar_visual:"Comparar visualmente",
  pdf_editar:"Adicionar texto, formas ou imagem", pdf_assinar_digital:"Assinar com certificado digital",
  pdf_pdfa:"Converter para PDF/A", pdf_para_word_ocr:"PDF para Word com OCR",
  pdf_extrair_imagens:"Extrair imagens do PDF", pdf_copiar:"Criar cópia do PDF",
  pdf_criar_formulario:"Criar formulário preenchível", pdf_workflow:"Automatizar fluxo de PDF"
};
function pdfCategoria(nome) {
  if (["pdf_juntar","pdf_unir_documentos","pdf_dividir","pdf_dividir_pares_impares","pdf_extrair","pdf_remover","pdf_organizar","pdf_girar","pdf_paginas_por_folha","pdf_imprimir_livreto"].includes(nome)) return "Organizar páginas";
  if (["pdf_imagens_para_pdf","pdf_documento_para_pdf","pdf_para_imagens","pdf_converter","pdf_html_para_pdf","pdf_para_word_ocr","pdf_para_excel","pdf_para_powerpoint","pdf_para_markdown","pdf_pdfa"].includes(nome)) return "Criar e converter";
  if (["pdf_cortar","pdf_marca","pdf_numeros","pdf_editar"].includes(nome)) return "Editar e anotar";
  if (["pdf_comprimir","pdf_reparar","pdf_ocr"].includes(nome)) return "Otimizar e reparar";
  if (["pdf_proteger","pdf_desbloquear","pdf_assinar","pdf_assinar_digital","pdf_censurar","pdf_metadados"].includes(nome)) return "Segurança e privacidade";
  if (["pdf_formularios","pdf_criar_formulario"].includes(nome)) return "Formulários e assinatura";
  return "Verificar e analisar";
}
function pdfAtual() { return pdfFerramentas.find(x => x.nome === $("#pdf-ferramenta").value); }
function desenharFiltrosPDF() {
  const busca = ($("#pdf-busca")?.value || "").trim().toLocaleLowerCase("pt-BR");
  const categorias = PDF_CATEGORIAS.filter(c => c === "Todas" || pdfFerramentas.some(f => pdfCategoria(f.nome) === c));
  $("#pdf-filtros").innerHTML = categorias.map(c => {
    const total = c === "Todas" ? pdfFerramentas.length : pdfFerramentas.filter(f => pdfCategoria(f.nome) === c).length;
    return `<button type="button" class="pdf-filtro ${pdfCategoriaAtiva === c ? "ativo" : ""}" data-pdf-categoria="${esc(c)}">${esc(c)} <span>${total}</span></button>`;
  }).join("");
  const lista = pdfFerramentas.filter(f => {
    const texto = [PDF_ROTULOS[f.nome] || f.nome, f.descricao, f.nome].join(" ").toLocaleLowerCase("pt-BR");
    return (pdfCategoriaAtiva === "Todas" || pdfCategoria(f.nome) === pdfCategoriaAtiva) && (!busca || texto.includes(busca));
  });
  $("#pdf-ferramentas-grid").innerHTML = lista.length ? lista.map(f => {
    const selecionada = $("#pdf-ferramenta").value === f.nome;
    const icone = {"Criar e converter":"⇄","Organizar páginas":"▤","Editar e anotar":"✎","Otimizar e reparar":"◈","Segurança e privacidade":"♢","Formulários e assinatura":"✒","Verificar e analisar":"⌕"}[pdfCategoria(f.nome)] || "▧";
    return `<button type="button" class="pdf-ferramenta ${selecionada ? "selecionada" : ""}" data-pdf-tool="${esc(f.nome)}" aria-pressed="${selecionada}">
      <span class="pdf-ferramenta-icone">${icone}</span><b>${esc(PDF_ROTULOS[f.nome] || f.nome.replaceAll("_"," "))}</b>
      <small>${esc(f.descricao || "")}</small></button>`;
  }).join("") : '<p class="sutil">Nenhuma ferramenta encontrada nesta categoria.</p>';
}
async function carregarPDF() {
  const estadoEl = $("#pdf-estado-inicial");
  try {
    const dados = await api("/api/pdf");
    pdfFerramentas = dados.ferramentas || [];
    if (!pdfFerramentas.length) throw new Error("Nenhuma ferramenta PDF foi registrada.");
    desenharFiltrosPDF(); desenharArquivosPDF();
    estadoEl.textContent = `${pdfFerramentas.length} ferramentas carregadas · processamento local` +
      (dados.dependencias_instaladas ? "" : " · algumas operações exigem instalar o extra PDF");
  } catch (e) { estadoEl.textContent = "⚠️ Não foi possível carregar o catálogo: " + e.message; }
}
function selecionarFerramentaPDF(nome) {
  const f = pdfFerramentas.find(x => x.nome === nome);
  if (!f) return;
  $("#pdf-ferramenta").value = nome;
  $("#pdf-operacao-selecionada").classList.remove("oculto");
  $("#pdf-estado-inicial").classList.add("oculto");
  $("#pdf-titulo-operacao").textContent = PDF_ROTULOS[nome] || nome.replaceAll("_"," ");
  desenharFiltrosPDF(); desenharParametrosPDF();
  $("#pdf-operacao-selecionada").scrollIntoView({behavior:"smooth",block:"nearest"});
}
function desenharArquivosPDF() {
  $("#pdf-lista-arquivos").innerHTML = pdfEnviados.length
    ? pdfEnviados.map((f,i) => `<div class="pdf-arquivo"><span>📄 ${esc(f.nome)}</span><small>${(f.tamanho/1048576).toFixed(2)} MB</small><button type="button" class="icone" data-pdf-remover="${i}" title="Remover da seleção">✕</button></div>`).join("")
    : '<p class="sutil">Nenhum documento adicionado ainda.</p>';
  $("#pdf-executar").disabled = !pdfEnviados.length || !pdfAtual();
}
function desenharParametrosPDF() {
  const f = pdfAtual();
  $("#pdf-descricao").textContent = f ? f.descricao : "";
  $("#pdf-parametros").innerHTML = (f ? Object.entries(f.parametros || {}) : []).map(([nome,info]) => {
    const tipo = info.type === "integer" || info.type === "number" ? "number" : "text";
    let valor = "";
    if (nome === "arquivo" && pdfEnviados[0]) valor = pdfEnviados[0].arquivo;
    if (nome === "arquivos" && pdfEnviados.length) valor = pdfEnviados.map(x=>x.arquivo).join(";");
    if ((nome === "arquivo_a" || nome === "arquivo1") && pdfEnviados[0]) valor = pdfEnviados[0].arquivo;
    if ((nome === "arquivo_b" || nome === "arquivo2" || nome === "certificado" || nome === "perfil_icc") && pdfEnviados[1]) valor = pdfEnviados[1].arquivo;
    const obrigatorio = (f.obrigatorios || []).includes(nome), sensivel = /senha|password/i.test(nome);
    return `<label>${esc(nome.replaceAll("_"," "))}${obrigatorio ? " *" : ""}<input class="campo" data-pdf-param="${esc(nome)}" type="${sensivel ? "password" : tipo}" ${sensivel ? 'autocomplete="new-password"' : ""} value="${esc(valor)}" placeholder="${esc(info.description || nome)}" ${obrigatorio && !valor ? "required" : ""}></label>`;
  }).join("");
  $("#pdf-executar").disabled = !pdfEnviados.length || !f;
}
$("#pdf-filtros").addEventListener("click", e => {
  const b = e.target.closest("[data-pdf-categoria]");
  if (!b) return; pdfCategoriaAtiva = b.dataset.pdfCategoria; desenharFiltrosPDF();
});
$("#pdf-busca").addEventListener("input", desenharFiltrosPDF);
$("#pdf-ferramentas-grid").addEventListener("click", e => {
  const b = e.target.closest("[data-pdf-tool]"); if (b) selecionarFerramentaPDF(b.dataset.pdfTool);
});
$("#pdf-limpar-operacao").addEventListener("click", () => {
  $("#pdf-ferramenta").value = ""; $("#pdf-operacao-selecionada").classList.add("oculto");
  $("#pdf-estado-inicial").classList.remove("oculto"); desenharFiltrosPDF();
});
$("#pdf-enviar").addEventListener("click", async () => {
  const arquivos = [...($("#pdf-arquivos").files || [])];
  if (!arquivos.length) { $("#pdf-estado-inicial").textContent = "Selecione pelo menos um documento."; return; }
  for (const arquivo of arquivos) {
    const extensao = arquivo.name.toLowerCase().split(".").pop();
    if (!["pdf","jpg","jpeg","png","tif","tiff","bmp","html","htm","doc","docx","xls","xlsx","ppt","pptx","odt","ods","odp","rtf","txt","csv","p12","pfx","icc"].includes(extensao)) {
      $("#pdf-estado-inicial").textContent = "Formato não aceito: " + extensao; continue;
    }
    $("#pdf-estado-inicial").textContent = "Enviando " + arquivo.name + "…";
    try {
      const r = await api("/api/pdf/upload?nome=" + encodeURIComponent(arquivo.name), {
        method:"POST",headers:{"Content-Type":"application/octet-stream"},body:arquivo,tempo:180000
      });
      pdfEnviados.push(r); desenharArquivosPDF();
    } catch(e) { $("#pdf-estado-inicial").textContent = "Falha no envio de " + arquivo.name + ": " + e.message; }
  }
  $("#pdf-arquivos").value = ""; desenharParametrosPDF();
  if (pdfEnviados.length) $("#pdf-estado-inicial").textContent = pdfEnviados.length + " arquivo(s) pronto(s) para processar.";
});
$("#pdf-lista-arquivos").addEventListener("click", e => {
  const b = e.target.closest("[data-pdf-remover]"); if (!b) return;
  pdfEnviados.splice(Number(b.dataset.pdfRemover),1); desenharArquivosPDF(); desenharParametrosPDF();
});
$("#pdf-executar").addEventListener("click", async () => {
  const f = pdfAtual(); if (!f) return;
  const argumentos = {};
  for (const campo of $$("[data-pdf-param]")) {
    const nome = campo.dataset.pdfParam, valor = campo.value.trim();
    if (valor === "" && !(f.obrigatorios || []).includes(nome)) continue;
    argumentos[nome] = campo.type === "number" ? Number(valor) : valor;
  }
  for (const nome of f.obrigatorios || []) {
    if (argumentos[nome] === "" || argumentos[nome] === undefined) {
      $("#pdf-estado").textContent = "Preencha o campo obrigatório: " + nome; return;
    }
  }
  $("#pdf-executar").disabled = true; $("#pdf-estado").textContent = "Processando localmente…";
  $("#pdf-resultado").textContent = "A operação está em andamento. Não feche o Optimus.";
  try {
    const r = await api("/api/pdf/executar",{method:"POST",json:{ferramenta:f.nome,argumentos},tempo:300000});
    const resultado = r.resultado || {};
    const mensagem = resultado.mensagem || resultado.resultado || resultado.texto || "Operação concluída.";
    const detalhes = Object.entries(resultado).filter(([k])=>!["mensagem","destino","zip","arquivos"].includes(k))
      .map(([k,v])=>`<div><b>${esc(k.replaceAll("_"," "))}:</b> ${esc(typeof v==="object"?JSON.stringify(v):v)}</div>`).join("");
    const links = (r.arquivos||[]).map(x=>`<a class="botao pequeno" href="/api/pdf/arquivo?nome=${encodeURIComponent(x.nome)}" download>⬇ Baixar ${esc(x.nome)}</a>`).join(" ");
    $("#pdf-resultado").innerHTML = `<p class="sucesso">✅ ${esc(mensagem)}</p>${detalhes}${links ? `<div class="linha">${links}</div>` : ""}`;
    $("#pdf-estado").textContent = "Operação concluída.";
  } catch(e) { $("#pdf-resultado").textContent = "Falha: " + e.message; $("#pdf-estado").textContent = "A operação não foi concluída."; }
  finally { $("#pdf-executar").disabled = !pdfEnviados.length; }
});

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
    estado.soExecutar = !!d.so_executar;
    const avisoAt = $("#aviso-atualizacao"), at = d.aviso_atualizacao;
    if (at && at.mensagem && !avisoAt.dataset.mostrado) {
      avisoAt.dataset.mostrado = "1";
      avisoAt.innerHTML = "🔄 " + esc(at.mensagem) + `<div class="linha"><button class="botao pequeno">Entendi</button></div>`;
      avisoAt.querySelector("button").onclick = () => avisoAt.classList.add("oculto");
      avisoAt.classList.remove("oculto");
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

// Modo "só executar": faz o pedido e não fala a resposta (confirmações continuam faladas).
function deveFalar(porVoz) { return !estado.soExecutar && (estado.falar || aoVivo.ligado || porVoz); }

async function acompanhar(tarefa, bolha, porVoz) {
  let desde = 0; let pendenteId = ""; let atual = bolha; let usada = false;
  let parcial = ""; let falouParcial = false;
  // Reavaliado a cada evento: se o usuário desligar o ao vivo ou o 🔈 no meio da
  // resposta, o Optimus para de falar em vez de continuar até o fim.
  const novaBolha = () => { if (usada) { atual = adicionarMensagem("optimus", "", {}); usada = false; } };
  let falhas = 0;
  while (true) {
    let d;
    try { d = await api(`/api/tarefa/${tarefa}?desde=${desde}`, { tempo: 15000 }); falhas = 0; }
    catch (e) {
      if (e.message === "senha") return;
      // Tarefa sumiu (o Optimus reiniciou) ou o servidor não responde há ~30 s: avisa e
      // libera a tela, em vez de ficar "Pensando…" para sempre.
      falhas += 1;
      if (/não encontrada/i.test(e.message) || falhas >= 30) {
        if (falouParcial) Voz.parar();
        $(".texto", atual).innerHTML = "<p>⚠️ Perdi a conexão com o Optimus durante a resposta. Se ele foi reiniciado, envie o pedido de novo.</p>";
        definirEstado("erro", "Sem conexão");
        return;
      }
      await new Promise((r) => setTimeout(r, 1000)); continue;
    }
    desde = d.total;
    for (const ev of d.eventos) {
      if (ev.tipo === "conversa") estado.conversa = ev.id;
      else if (ev.tipo === "pensando") definirEstado("pensando", ev.passo > 1 ? `Pensando (passo ${ev.passo})…` : "Pensando…");
      else if (ev.tipo === "parcial") {
        novaBolha();
        parcial += ev.texto;
        $(".texto", atual).innerHTML = markdown(parcial);
        legenda("optimus", parcial);
        if (deveFalar(porVoz)) { Voz.adicionarParcial(ev.texto); falouParcial = true; }
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
        if (deveFalar(porVoz)) { if (falouParcial) Voz.finalizar(); else Voz.falar(ev.texto); }
        else if (falouParcial) Voz.parar();
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
  if (estado.falar || aoVivo.ligado) Voz.falar(`Atenção. Posso ${p.motivo}? ${critico ? "Diga confirmo para aprovar." : ""}`);
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
    aoVivo.ligado = false; Voz.pararEscuta(); Voz.parar();
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
      <div class="acoes">${!p.embutida ? `<button class="icone" data-apagar-persona="${esc(p.chave)}" title="Apagar">🗑️</button>` : `<span class="selo" title="Persona do sistema: pode editar, não excluir">sistema</span>`}</div>
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

// ---------- Biblioteca de documentos ----------
async function buscarBiblioteca(consulta) {
  const status = $("#biblioteca-busca-status"), saida = $("#biblioteca-resultados");
  status.textContent = "Pesquisando nos documentos locais…";
  saida.innerHTML = "";
  try {
    const d = await api("/api/biblioteca?q=" + encodeURIComponent(consulta));
    status.textContent = d.total ? d.total + " trecho(s) encontrado(s)." : "Nenhum trecho encontrado. Tente outros termos ou confira se a pasta foi indexada.";
    saida.innerHTML = (d.resultados || []).map((r) => {
      const citacao = String(r.citacao || "");
      return `<article class="cartao"><b>${esc(r.titulo || "Documento")}</b>
        <p class="sutil">${esc(r.fonte || "")}</p>
        <p>${esc(r.trecho || "")}</p>
        <small class="sutil">Fonte para citação: ${esc(citacao)}</small></article>`;
    }).join("");
  } catch (erro) {
    status.textContent = "Falha na pesquisa: " + erro.message;
  }
}
$("#form-biblioteca-busca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const consulta = e.currentTarget.elements.q.value.trim();
  if (consulta) await buscarBiblioteca(consulta);
});
async function carregarBiblioteca() {
  const lista = $("#biblioteca-lista");
  try {
    const d = await api("/api/biblioteca");
    $("#biblioteca-total").textContent = String(d.total || 0);
    lista.innerHTML = (d.documentos || []).map((x) => {
      const fonte = String(x.fonte || "").replace(/^biblioteca:/, "");
      return `<li><span>📄 <b>${esc(x.titulo || fonte.split(/[\\\\/]/).pop() || "Documento")}</b><br><small class="sutil">${esc(fonte)} · ${Number(x.trechos || 0)} trecho(s)</small></span></li>`;
    }).join("") || '<li class="sutil">Nenhum documento indexado. Informe uma pasta acima para começar.</li>';
  } catch (erro) { lista.innerHTML = `<li class="erro">${esc(erro.message)}</li>`; }
}
$("#form-biblioteca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget, status = $("#biblioteca-status");
  const botao = form.querySelector('button[type="submit"]');
  botao.disabled = true; status.textContent = "Indexando arquivos localmente…";
  try {
    const r = await api("/api/biblioteca", {method:"POST", json:{pasta:form.elements.pasta.value.trim(), recursivo:form.elements.recursivo.checked}, tempo:300000});
    status.textContent = r.mensagem + (r.erros?.length ? " Erros: " + r.erros.map(x => x.arquivo + ": " + x.erro).join(" | ") : "");
    await carregarBiblioteca();
  } catch (erro) { status.textContent = "Falha na indexação: " + erro.message; }
  finally { botao.disabled = false; }
});
$("#atualizar-biblioteca").addEventListener("click", carregarBiblioteca);
$("#form-biblioteca-esquecer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget, pasta = form.elements.pasta.value.trim();
  if (!pasta || !confirm("Remover do conhecimento local os documentos desta pasta? Os arquivos originais não serão apagados.")) return;
  try {
    const r = await api("/api/biblioteca", {method:"DELETE", json:{pasta}});
    $("#biblioteca-status").textContent = r.mensagem; form.reset(); await carregarBiblioteca();
  } catch (erro) { $("#biblioteca-status").textContent = "Falha ao remover: " + erro.message; }
});

// ---------- Ações ----------
async function carregarAcoes() {
  const d = await api("/api/acoes");
  $("#lista-acoes").innerHTML = d.acoes.map((a) => `<tr><td>${esc(a.quando)}</td><td><b>${esc(a.ferramenta)}</b></td><td><code>${esc(JSON.stringify(a.argumentos))}</code></td>
    <td><span class="nivel ${esc(a.nivel)}">${esc(a.nivel)}</span></td><td>${{ automatica: "✅ automática", aprovada: "👍 aprovada", negada: "❌ negada", bloqueada: "⛔ bloqueada" }[a.decisao] || esc(a.decisao)}</td></tr>`).join("")
    || '<tr><td colspan="5" class="sutil">Nenhuma ação ainda.</td></tr>';
}

// ---------- Atualização pelo GitHub ----------
$("#verificar-atualizacao").addEventListener("click", async () => {
  const estadoEl = $("#atualizacao-estado"); const baixar = $("#baixar-atualizacao");
  estadoEl.textContent = "Verificando no GitHub…"; baixar.classList.add("oculto");
  try {
    const d = await api("/api/atualizacao");
    if (d.erro) { estadoEl.textContent = "⚠️ " + d.erro; return; }
    if (d.atualizado) { estadoEl.textContent = "✅ " + (d.mensagem || "Você já está na versão mais nova."); return; }
    estadoEl.textContent = `🚀 ${d.mensagem || "Há atualização disponível."} Clique em "Baixar e aplicar".`;
    baixar.classList.remove("oculto");
  } catch (e) { estadoEl.textContent = "⚠️ Não consegui verificar: " + e.message; }
});
$("#baixar-atualizacao").addEventListener("click", async (ev) => {
  const estadoEl = $("#atualizacao-estado"); ev.target.disabled = true;
  estadoEl.textContent = "Baixando e aplicando (sem perder seus dados)…";
  try {
    const d = await api("/api/atualizacao", { method: "POST", json: {} });
    if (d.erro || d.ok === false) { estadoEl.textContent = "⚠️ " + (d.erro || d.mensagem); }
    else { estadoEl.textContent = "✅ " + (d.mensagem || "Atualizado!") + " Reinicie o Optimus para usar a nova versão."; ev.target.classList.add("oculto"); }
  } catch (e) { estadoEl.textContent = "⚠️ Falha ao atualizar: " + e.message; }
  finally { ev.target.disabled = false; }
});

// ---------- Celular e agenda ----------
function desenharCelular(d) {
  const estadoEl = $("#celular-estado"); const qr = $("#celular-qr");
  const figura = (svg, legenda) => svg ? `<figure class="qr">${svg}<figcaption>${esc(legenda)}</figcaption></figure>` : "";
  qr.innerHTML = figura(d.qr, "Abrir no celular") + figura(d.agenda_qr, "Assinar a agenda");
  const partes = [];
  if (d.dica) partes.push("⚠️ " + esc(d.dica));
  if (d.ligado) {
    partes.push(`✅ Acesso pela rede local ligado. Conecte o celular ao mesmo Wi-Fi, leia o QR Code ou abra <code>${esc(d.url)}</code> e entre com a senha. Para usar de fora de casa (4G/5G ou outro Wi-Fi), ative o Cloudflare Tunnel na seção Acesso externo abaixo.`);
    partes.push("Se o celular não abrir, libere o Optimus (Python) no firewall do computador para redes privadas.");
    if (!d.qr) partes.push("Para ver o QR code, instale: <code>pip install segno</code>");
  }
  partes.push(`Agenda: <code>${esc(d.agenda)}</code>`);
  estadoEl.innerHTML = partes.join("<br>");
  $("#trocar-agenda").classList.remove("oculto");
  $("#desligar-celular").classList.toggle("oculto", !d.ligado);
  $("#ligar-celular").textContent = d.ligado ? "🔑 Trocar senha do celular" : "📶 Ligar acesso pelo celular";
}
async function mostrarCelular(nova) {
  const estadoEl = $("#celular-estado");
  estadoEl.textContent = "Carregando…";
  try {
    desenharCelular(await api("/api/celular" + (nova ? "?nova_chave=1" : "")));
    await mostrarTunel();
  } catch (e) { estadoEl.textContent = "⚠️ " + e.message; }
}
$("#mostrar-celular").addEventListener("click", () => mostrarCelular(false));
$("#trocar-agenda").addEventListener("click", () => mostrarCelular(true));
$("#ligar-celular").addEventListener("click", async (ev) => {
  const estadoEl = $("#celular-estado"); const campo = $("#celular-senha");
  ev.target.disabled = true; estadoEl.textContent = "Ligando…";
  try {
    const d = await api("/api/celular", { method: "POST", json: { senha: campo.value } });
    if (d.erro) { estadoEl.textContent = "⚠️ " + d.erro; return; }
    campo.value = ""; desenharCelular(d);
  } catch (e) { estadoEl.textContent = "⚠️ " + e.message; }
  finally { ev.target.disabled = false; }
});
$("#desligar-celular").addEventListener("click", async () => {
  try { desenharCelular(await api("/api/celular/desligar", { method: "POST" })); }
  catch (e) { $("#celular-estado").textContent = "⚠️ " + e.message; }
});

// ---------- Acesso externo seguro (Cloudflare Tunnel) ----------
let consultaTunelId = 0;
function desenharTunel(d) {
  const estadoEl = $("#tunel-estado");
  const qr = $("#tunel-qr");
  const figura = (svg, legenda) => svg
    ? "<figure class=\"qr\">" + svg + "<figcaption>" + esc(legenda) + "</figcaption></figure>" : "";
  qr.innerHTML = figura(d.qr, "Abrir Optimus pela internet") +
    figura(d.agenda_qr, "Assinar agenda pela internet");
  if (d.erro) estadoEl.textContent = "⚠️ " + d.erro;
  else if (d.url) estadoEl.innerHTML = "✅ Acesso HTTPS ativo: <a href=\"" + esc(d.url) + "\" target=\"_blank\" rel=\"noopener noreferrer\">" + esc(d.url) + "</a><br>Leia o QR Code ou abra o endereço em qualquer rede (4G/5G, Wi-Fi externo ou computador). Entre com a senha exclusiva. O endereço é temporário e o computador precisa permanecer ligado e conectado à internet." + (d.agenda ? "<br>Agenda externa: <a href=\"" + esc(d.agenda) + "\" target=\"_blank\" rel=\"noopener noreferrer\">Assinar agenda</a>" : "");
  else if (d.iniciando) estadoEl.textContent = "⏳ Conectando ao Cloudflare… O Optimus verificará automaticamente até o endereço HTTPS e os QR Codes ficarem prontos.";
  else estadoEl.textContent = "Acesso externo desligado.";
  $("#desligar-tunel").classList.toggle("oculto", !d.ligado && !d.iniciando);
  $("#ligar-tunel").classList.toggle("oculto", !!d.ligado || !!d.iniciando);
}
async function acompanharTunel(id) {
  let intervalo = 1000;
  while (id === consultaTunelId) {
    await new Promise(resolve => setTimeout(resolve, intervalo));
    if (id !== consultaTunelId) return;
    try {
      const d = await api("/api/tunel");
      if (id !== consultaTunelId) return;
      desenharTunel(d);
      if (!d.iniciando) return;
      intervalo = Math.min(5000, Math.round(intervalo * 1.35));
    } catch (e) {
      if (id !== consultaTunelId) return;
      $("#tunel-estado").textContent = "⚠️ " + e.message + " Tentarei novamente automaticamente.";
      intervalo = Math.min(5000, Math.round(intervalo * 1.5));
    }
  }
}
async function mostrarTunel() {
  const id = ++consultaTunelId;
  const el = $("#tunel-estado");
  el.textContent = "Verificando acesso externo…";
  try {
    const d = await api("/api/tunel");
    if (id !== consultaTunelId) return;
    desenharTunel(d);
    if (d.iniciando) void acompanharTunel(id);
  } catch (e) {
    if (id === consultaTunelId) el.textContent = "⚠️ " + e.message;
  }
}
$("#ligar-tunel").addEventListener("click", async () => {
  const campo = $("#tunel-senha"), valor = campo.value;
  const el = $("#tunel-estado");
  if (valor.length < 12) { el.textContent = "Use uma senha exclusiva com pelo menos 12 caracteres."; return; }
  const id = ++consultaTunelId;
  $("#ligar-tunel").disabled = true;
  el.textContent = "Iniciando Cloudflare Tunnel…";
  try {
    const d = await api("/api/tunel", { method: "POST", json: { senha: valor }, tempo: 90000 });
    if (id !== consultaTunelId) return;
    senha = valor;
    try { sessionStorage.setItem("optimus_senha", senha); } catch (e) {}
    campo.value = "";
    desenharTunel(d);
    if (d.iniciando) void acompanharTunel(id);
  } catch (e) {
    if (id !== consultaTunelId) return;
    senha = valor;
    try { sessionStorage.setItem("optimus_senha", senha); } catch (err) {}
    el.textContent = "⚠️ " + e.message;
  } finally { $("#ligar-tunel").disabled = false; }
});
$("#desligar-tunel").addEventListener("click", async () => {
  ++consultaTunelId;
  const el = $("#tunel-estado");
  el.textContent = "Encerrando túnel…";
  try { desenharTunel(await api("/api/tunel/desligar", { method: "POST", json: {} })); }
  catch (e) { el.textContent = "⚠️ " + e.message; }
});
$("#atualizar-tunel").addEventListener("click", mostrarTunel);

// ---------- Casa ----------
let vigiaCameras = null;
async function atualizarHomeAssistantGerenciado() {
  const diag = $("#ha-gerenciado-diagnostico"), badge = $("#ha-gerenciado-badge");
  const status = $("#ha-gerenciado-status"), abrir = $("#ha-gerenciado-abrir");
  try {
    const d = await api("/api/casa/gerenciado");
    const rt = d.runtime || {}, c = d.container || {}, tarefa = d.tarefa || {};
    badge.textContent = c.rodando ? "Em execução" : c.instalado ? "Instalado / parado" : rt.docker_instalado ? (rt.docker_ativo === null ? "Permissão necessária" : rt.docker_ativo ? "Pronto para instalar" : "Docker parado") : "Não instalado";
    diag.textContent = [
      "Sistema: " + (rt.sistema || "desconhecido"),
      "Docker: " + (rt.docker_instalado ? (rt.docker_ativo === null ? "permissão administrativa necessária" : rt.docker_ativo ? "ativo " + (rt.docker_versao || "") : "instalado, mas parado") : "não instalado"),
      "Home Assistant: " + (c.rodando ? "rodando" : c.instalado ? c.estado : "não instalado"),
      d.nota || "", rt.observacao || "", d.erro || ""
    ].filter(Boolean).join(" · ");
    abrir.disabled = !c.rodando;
    abrir.dataset.url = d.url || "";
    if (tarefa.estado === "executando") {
      status.textContent = tarefa.mensagem || "Operação em andamento…";
      return true;
    }
    if (tarefa.estado === "falhou") status.textContent = "⚠️ " + (tarefa.erro || "A operação falhou.");
    else if (tarefa.estado === "concluido") status.textContent = "✅ " + (tarefa.mensagem || "Operação concluída.");
    const logs = $("#ha-gerenciado-logs");
    if (tarefa.resultado && tarefa.resultado.logs) {
      logs.textContent = tarefa.resultado.logs;
      logs.classList.remove("oculto");
    }
    return false;
  } catch (e) {
    badge.textContent = "Falha no diagnóstico";
    diag.textContent = "Não foi possível consultar o gerenciador: " + e.message;
    return false;
  }
}
async function executarAcaoHomeAssistant(acao) {
  const status = $("#ha-gerenciado-status");
  const botoes = $$("#ha-gerenciado button");
  if (acao === "desinstalar" && !window.confirm("Remover o container Home Assistant? Os dados e backups serão preservados.")) return;
  botoes.forEach((b) => { b.disabled = true; });
  status.textContent = "Solicitando operação ao Optimus…";
  try {
    await api("/api/casa/gerenciado", { method: "POST", json: { acao }, tempo: 30000 });
    let emAndamento = true;
    const inicio = Date.now();
    while (emAndamento && Date.now() - inicio < 20 * 60 * 1000) {
      await new Promise((resolve) => setTimeout(resolve, 1800));
      emAndamento = await atualizarHomeAssistantGerenciado();
    }
    if (emAndamento) status.textContent = "A operação continua em segundo plano. Use Atualizar status para acompanhar.";
  } catch (e) {
    status.textContent = "⚠️ " + e.message;
  } finally {
    botoes.forEach((b) => { b.disabled = false; });
    await atualizarHomeAssistantGerenciado();
  }
}
$("#ha-gerenciado-instalar").addEventListener("click", () => executarAcaoHomeAssistant("instalar"));
$("#ha-gerenciado-atualizar").addEventListener("click", atualizarHomeAssistantGerenciado);
$("#ha-gerenciado-abrir").addEventListener("click", () => {
  const url = $("#ha-gerenciado-abrir").dataset.url;
  if (url) window.open(url, "_blank", "noopener,noreferrer");
});
$$("[data-ha-acao]").forEach((b) => b.addEventListener("click", () => executarAcaoHomeAssistant(b.dataset.haAcao)));

async function carregarCasa() {
  await atualizarHomeAssistantGerenciado();
  const d = await api("/api/config");
  $("#casa-url").value = d.config.casa.url || ""; $("#casa-token").value = d.config.casa.token || "";
  try {
    const c = await api("/api/cameras");
    $("#cameras").innerHTML = c.cameras.map((x) => `<figure class="cartao camera"><img data-camera="${esc(x.id)}" alt="${esc(x.nome)}">${String(x.id).startsWith("ip:") ? `<button class="icone" data-apagar-camera="${esc(x.id)}" title="Remover câmera">🗑️</button>` : ""}<figcaption>${esc(x.nome)} <span class="sutil">prévia ~1,2 s</span></figcaption></figure>`).join("")
      || '<p class="sutil">Nenhuma câmera adicionada ainda. Adicione uma câmera Wi-Fi acima, ligue uma webcam no cabo USB, ou conecte o Home Assistant.</p>';
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
async function testarHomeAssistant() {
  const status = $("#casa-conexao-status");
  status.textContent = "Testando endereço e token…";
  try {
    const r = await api("/api/casa/testar", { method: "POST", json: {
      url: $("#casa-url").value.trim(), token: $("#casa-token").value.trim()
    }});
    status.textContent = r.ok ? "✅ " + r.mensagem : "⚠️ " + (r.erro || "Não foi possível conectar.");
    return !!r.ok;
  } catch (e) {
    status.textContent = "⚠️ " + e.message;
    return false;
  }
}
$("#casa-testar").onclick = testarHomeAssistant;
$("#casa-onvif-descobrir").onclick = async () => {
  const saida = $("#casa-onvif-resultados");
  saida.textContent = "Procurando câmeras ONVIF na rede local…";
  try {
    const d = await api("/api/cameras/descobrir", { method: "POST", json: {} });
    saida.innerHTML = d.total ? (d.itens || []).map((item) =>
      `<article class="cartao"><b>Câmera ONVIF encontrada</b>
        <p>IP: ${esc(item.ip || "não informado")}</p>
        <p>Endpoint: ${(item.endpoints || []).map(esc).join("<br>")}</p>
        <p class="sutil">Autenticação: não verificada. Informe abaixo o endereço RTSP ou snapshot e as credenciais da câmera.</p></article>`
    ).join("") : `<p class="sutil">${esc(d.mensagem || "Nenhuma câmera encontrada.")}</p>`;
  } catch (e) { saida.textContent = "Falha na descoberta: " + e.message; }
};
$("#casa-salvar").onclick = async () => {
  const status = $("#casa-conexao-status");
  status.textContent = "Salvando configuração local…";
  try {
    await api("/api/config", { method: "POST", json: { casa: {
      url: $("#casa-url").value.trim(), token: $("#casa-token").value.trim()
    }}});
    if (await testarHomeAssistant()) executarFerramenta("Liste os aparelhos da minha casa");
  } catch (e) { status.textContent = "⚠️ Não foi possível salvar: " + e.message; }
};
$("#casa-atualizar").onclick = () => executarFerramenta("Liste os aparelhos da minha casa e o estado de cada um");
$("#casa-diagnostico").onclick = () => executarFerramenta("Execute casa_diagnostico e informe quais integrações, dispositivos e câmeras estão realmente disponíveis.");
$("#casa-bluetooth").onclick = () => executarFerramenta("Procure aparelhos Bluetooth por perto");
$("#casa-rede").onclick = () => executarFerramenta("Quais aparelhos estão conectados na rede da casa?");
$("#cam-adicionar").onclick = async () => {
  const est = $("#cam-estado"); const url = $("#cam-url").value.trim();
  if (!url) { est.textContent = "⚠️ Informe o endereço ou link da câmera."; return; }
  est.textContent = "Adicionando…";
  try {
    const r = await api("/api/cameras", { method: "POST", json: {
      nome: $("#cam-nome").value.trim(), url, usuario: $("#cam-usuario").value.trim(), senha: $("#cam-senha").value } });
    if (r.erro) { est.textContent = "⚠️ " + r.erro; return; }
    est.textContent = "✅ Câmera adicionada.";
    $("#cam-nome").value = $("#cam-url").value = $("#cam-usuario").value = $("#cam-senha").value = "";
    carregarCasa();
  } catch (e) { est.textContent = "⚠️ " + e.message; }
};
$("#cameras").addEventListener("click", async (e) => {
  const rem = e.target.closest("[data-apagar-camera]"); if (!rem) return;
  await api("/api/cameras/" + encodeURIComponent(rem.dataset.apagarCamera), { method: "DELETE" });
  carregarCasa();
});

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
  if (window.innerWidth <= 760) { entrada.placeholder = "Fale com o Optimus…"; $("#botao-ao-vivo").title = "Ao vivo"; }
  irPara(modoHud ? "hud" : "chat");

  // A animação nunca pode bloquear a aplicação. Mesmo se algum script de HUD falhar,
  // removemos a camada de abertura e deixamos a interface apresentar o erro real.
  const boot = document.getElementById("boot");
  const liberarBoot = () => { if (boot && boot.isConnected) boot.remove(); };
  const watchdogBoot = setTimeout(liberarBoot, 4000);
  try { await Promise.race([Promise.resolve(Hud.boot()), new Promise(resolve => setTimeout(resolve, 2500))]); }
  catch (erro) { console.error("Falha na animação de inicialização:", erro); }
  finally { clearTimeout(watchdogBoot); liberarBoot(); }

  // Uma API indisponível não pode impedir o carregamento das demais partes da tela.
  const resultados = await Promise.allSettled([
    atualizarSistema(), carregarPersonas(), carregarConversas()
  ]);
  const falhas = resultados.filter(x => x.status === "rejected");
  if (falhas.length) {
    console.error("Falha parcial na inicialização do Optimus:", falhas.map(x => x.reason));
    if (falhas.length === resultados.length) definirEstado("erro", "Servidor sem resposta — verifique a conexão");
    else if ($("#estado-texto").textContent === "Pronto") definirEstado("erro", "Inicialização parcial — consulte a conexão");
  }
  if ("Notification" in window && Notification.permission === "default") {
    try { await Notification.requestPermission(); } catch (erro) { console.debug("Notificações indisponíveis:", erro); }
  }
}
iniciar().catch(erro => {
  console.error("Falha crítica ao iniciar o Optimus:", erro);
  const boot = document.getElementById("boot"); if (boot) boot.remove();
  definirEstado("erro", "Falha ao iniciar: " + (erro.message || "erro inesperado"));
});
setInterval(atualizarSistema, 4000);

// ---------- Gestos pela câmera (veja gestos.js) ----------
function executarGesto(gesto, rotulo) {
  avisoVoz(`Gesto: ${rotulo}`);
  if (gesto === "Open_Palm") { Voz.parar(); if (estado.ocupado) $("#parar").click(); }
  else if (gesto === "Thumb_Up" && confirmacaoAberta) {
    // Ação crítica nunca é aprovada só com um gesto: precisa do botão ou de “confirmo”.
    if (confirmacaoAberta.critico) avisoVoz("⛔ Ação crítica: aprove no botão ou diga “confirmo”.");
    else confirmacaoAberta.responder(true);
  } else if (gesto === "Thumb_Down" && confirmacaoAberta) confirmacaoAberta.responder(false);
  else if (gesto === "Victory") alternarAoVivo(!aoVivo.ligado);
  else if (gesto === "Pointing_Up" && !estado.ocupado && !gravandoManual) mic.click();
  else if (gesto === "Closed_Fist") { botaoFalar.click(); avisoVoz(estado.falar ? "🔊 Respostas em voz ligadas." : "🔇 Respostas em voz desligadas."); }
  else if (gesto === "ILoveYou") irPara(modoHud && telaAtual() === "chat" ? "chat" : "hud");
  else if (gesto === "Swipe_Left" || gesto === "Swipe_Right") trocarTelaPorGesto(gesto === "Swipe_Right" ? 1 : -1);
  else if (gesto === "Swipe_Up" || gesto === "Swipe_Down") rolarPorGesto(gesto === "Swipe_Up" ? 1 : -1);
}
function telaAtual() {
  const t = document.querySelector(".tela.ativa");
  return t ? t.id.replace("tela-", "") : "chat";
}
function trocarTelaPorGesto(direcao) {
  const telas = Array.from(document.querySelectorAll(".menu button[data-tela]")).map((b) => b.dataset.tela);
  const atual = telaAtual() === "chat" ? (modoHud ? "hud" : "chat") : telaAtual();
  const i = Math.max(0, telas.indexOf(atual));
  irPara(telas[(i + direcao + telas.length) % telas.length]);
}
function rolarPorGesto(direcao) {
  // No chat rola as mensagens; nas outras telas, a própria tela.
  const alvo = telaAtual() === "chat" ? document.getElementById("mensagens") : document.querySelector(".tela.ativa");
  const caixa = alvo && alvo.scrollHeight > alvo.clientHeight ? alvo : document.scrollingElement;
  caixa.scrollBy({ top: direcao * caixa.clientHeight * 0.6, behavior: "smooth" });
}
function mostrarDicaGesto(info, temMao) {
  const dica = document.getElementById("gestos-dica");
  if (!dica) return;
  if (!temMao) { dica.textContent = "Mostre a mão para a câmera"; dica.style.setProperty("--progresso", "0"); return; }
  if (!info) { dica.textContent = "✋ mão vista"; dica.style.setProperty("--progresso", "0"); return; }
  dica.textContent = GESTOS_ROTULOS[info.gesto] || "";
  dica.style.setProperty("--progresso", String(info.progresso));
}
async function alternarGestos(ligar, idCamera) {
  const botao = $("#botao-gestos"), video = $("#gestos-video");
  if (!ligar) {
    Gestos.desligar(); video.classList.add("oculto"); document.getElementById("gestos-dica").classList.add("oculto");
    botao.classList.remove("ligado"); botao.textContent = "✋ Gestos";
    return;
  }
  botao.disabled = true; botao.textContent = "✋ Carregando…";
  let id = idCamera;
  if (id === undefined) { try { id = localStorage.getItem("optimus_camera_gestos") || ""; } catch (e) { id = ""; } }
  try {
    try { await Gestos.ligar(executarGesto, video, id, mostrarDicaGesto); }
    catch (e) { if (!id || e.name === "NotAllowedError") throw e; await Gestos.ligar(executarGesto, video, "", mostrarDicaGesto); } // câmera salva foi desligada
    video.classList.remove("oculto"); document.getElementById("gestos-dica").classList.remove("oculto");
    botao.classList.add("ligado"); botao.textContent = "✋ Gestos ligados";
    avisoVoz("Gestos: ✋ parar · 👍 aprovar · 👎 negar · ✌️ ao vivo · ☝️ falar · ✊ voz liga/desliga · 🤟 Núcleo/Conversas · 👈👉 trocar de tela · 👆👇 rolar. Segure o gesto parado por meio segundo. Clique no vídeo para trocar de câmera.");
  } catch (e) {
    botao.textContent = "✋ Gestos";
    avisoVoz("⚠️ Gestos: " + (e.name === "NotAllowedError" ? "libere a câmera para este site (cadeado na barra de endereço)."
      : e.name === "NotFoundError" ? "não achei nenhuma câmera ligada." : e.message));
  }
  botao.disabled = false;
}
$("#botao-gestos").onclick = () => alternarGestos(!Gestos.ligado);
// Webcam por cabo + a do notebook: clique na prévia para passar para a próxima câmera.
$("#gestos-video").onclick = async () => {
  const lista = await Gestos.cameras();
  if (lista.length < 2) { avisoVoz("Só achei uma câmera."); return; }
  let atual = ""; try { atual = localStorage.getItem("optimus_camera_gestos") || ""; } catch (e) {}
  const proxima = lista[(lista.findIndex((c) => c.deviceId === atual) + 1) % lista.length];
  try { localStorage.setItem("optimus_camera_gestos", proxima.deviceId); } catch (e) {}
  Gestos.desligar();
  await alternarGestos(true, proxima.deviceId);
  avisoVoz(`Câmera dos gestos: ${proxima.label || "câmera " + (lista.indexOf(proxima) + 1)}`);
};
