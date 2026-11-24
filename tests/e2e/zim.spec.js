const { test, expect } = require("@playwright/test");

test("biblioteca ZIM carrega catálogo local e atualiza sem erros", async ({ page }) => {
  const erros = [];
  page.on("pageerror", (erro) => erros.push(erro.message));
  page.on("console", (msg) => { if (msg.type() === "error") erros.push(msg.text()); });
  await page.goto("/");
  await page.locator('[data-tela="zim"]').click();
  await expect(page.getByRole("heading", { name: "Conhecimento offline" })).toBeVisible();
  await expect(page.locator("#zim-status")).toContainText("Catálogo atualizado");
  await expect(page.locator("#zim-resumo")).toContainText("Arquivos");
  await page.locator("#zim-atualizar").click();
  await expect(page.locator("#zim-status")).toContainText("Catálogo atualizado");
  expect(erros).toEqual([]);
});


test("biblioteca ZIM explica incompatibilidade quando a API instalada não tem a rota", async ({ page }) => {
  await page.route("**/api/zim", (route) => route.fulfill({
    status: 404, contentType: "application/json",
    body: JSON.stringify({ erro: "rota não encontrada" })
  }));
  await page.goto("/");
  await page.locator('[data-tela="zim"]').click();
  await expect(page.locator("#zim-status")).toContainText(/processo Python do Optimus ainda está carregado com o servidor antigo/i);
  await expect(page.locator("#zim-status")).toContainText(/feche completamente o Optimus/i);
});


test("importa o conteúdo inicial oficial do NOMAD pela ação explícita", async ({ page }) => {
  await page.route("**/api/zim/nomad-inicial", (route) => route.fulfill({ json: {
    ok: true, arquivo: "wikipedia_en_100_mini_2026-01.zim",
    tamanho_bytes: 4537782, mensagem: "Mini-Wikipédia inicial do Project NOMAD adicionada e validada."
  } }));
  await page.route("**/api/zim/status", (route) => route.fulfill({ json: {
    arquivos_zim_disponiveis: 1, artigos_indexados: 0, trechos: 0,
    com_embeddings: 0, modo_busca: "indisponivel", pronto: false,
    mensagem: "Conteúdo disponível; ainda não indexado."
  } }));
  await page.route("**/api/zim", (route) => route.fulfill({ json: {
    total: 1, tamanho_total_bytes: 4537782,
    arquivos: [{ nome: "wikipedia_en_100_mini_2026-01.zim", tamanho_bytes: 4537782, modificado_em: 1 }],
    pasta_configurada: true,
    kiwix: { instalado: true, gerenciado: true, versao: "3.8.2", executando: false, suportado: true }
  } }));
  await page.goto("/");
  await page.locator('[data-tela="zim"]').click();
  await page.locator("#zim-nomad-inicial").click();
  await expect(page.locator("#zim-lista")).toContainText("wikipedia_en_100_mini_2026-01.zim");
});
