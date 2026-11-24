const { test, expect } = require("@playwright/test");

test("Central de módulos usa estado gerenciado do Kiwix e valida daemon Docker", async ({ page }) => {
  await page.route("**/api/modulos", (route) => route.fulfill({ json: { modulos: [
    { id: "Optimus Core", nome: "Optimus Core", descricao: "Núcleo", estado: "nativo", detalhe: "Parte integrante" },
    { id: "Ollama", nome: "Ollama", descricao: "Modelos locais", estado: "disponivel", detalhe: "Respondendo em 127.0.0.1:11434" },
    { id: "Kiwix", nome: "Kiwix", descricao: "Leitor ZIM", estado: "instalado_parado", detalhe: "Kiwix Tools 3.8.2 instalado na pasta privada do Optimus; leitor parado até solicitação", gerenciado: true },
    { id: "Docker", nome: "Docker", descricao: "Runtime", estado: "instalado_parado", detalhe: "Docker CLI instalado, mas daemon indisponível: Cannot connect" }
  ] } }));
  await page.route("**/api/modulos/recursos", (route) => route.fulfill({ json: { recursos: {
    cpu_percentual: 12, cpu_nucleos_fisicos: 2, cpu_nucleos_logicos: 4,
    memoria_total_bytes: 7000000000, memoria_disponivel_bytes: 1400000000,
    memoria_percentual: 80, disco_total_bytes: 200000000000,
    disco_livre_bytes: 50000000000, disco_percentual: 75, processos: 100,
    uptime_segundos: 3600
  } } }));
  await page.goto("/");
  await page.locator('[data-tela="modulos"]').click();
  await expect(page.locator("#modulos-grade")).toContainText("Kiwix");
  await expect(page.locator("#modulos-grade")).toContainText("Instalado · parado");
  await expect(page.locator("#modulos-grade")).toContainText("pasta privada do Optimus");
  await expect(page.locator("#modulos-grade")).toContainText("daemon indisponível");
  await expect(page.locator("#modulos-grade")).toContainText("Ollama");
  await expect(page.locator("#modulos-grade")).toContainText("Disponível");
});

test("biblioteca sem arquivos não anuncia busca ativa nem solicita embeddings", async ({ page }) => {
  await page.route("**/api/zim", (route) => route.fulfill({ json: {
    total: 0, tamanho_total_bytes: 0, arquivos: [], pasta_configurada: true,
    kiwix: { instalado: true, gerenciado: true, versao: "3.8.2", executando: false, suportado: true }
  } }));
  await page.route("**/api/zim/status", (route) => route.fulfill({ json: {
    arquivos: [], arquivos_zim_disponiveis: 0, artigos_indexados: 0,
    trechos: 0, com_embeddings: 0, modo_busca: "indisponivel", pronto: false,
    mensagem: "Nenhum arquivo ZIM foi adicionado à biblioteca."
  } }));
  await page.route("**/api/zim/indexar", (route) => route.fulfill({ json: {
    ok: false, sem_arquivos: true,
    mensagem: "Nenhum arquivo ZIM foi encontrado. Adicione um arquivo .zim à pasta biblioteca_zim antes de indexar.",
    estado: { arquivos_zim_disponiveis: 0, artigos_indexados: 0, trechos: 0, modo_busca: "indisponivel", pronto: false }
  } }));
  await page.goto("/");
  await page.locator('[data-tela="zim"]').click();
  await expect(page.locator("#zim-index-status")).toContainText("Nenhum arquivo ZIM");
  await expect(page.locator("#zim-index-status")).not.toContainText("busca lexical ativa");
  await page.locator("#zim-indexar").click();
  await expect(page.locator("#zim-index-status")).toContainText("Adicione um arquivo .zim");
  await expect(page.locator("#zim-index-status")).not.toContainText("Modo lexical");
});
