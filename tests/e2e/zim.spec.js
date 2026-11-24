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
  await expect(page.locator("#zim-status")).toContainText(/API em execução não oferece as rotas/i);
  await expect(page.locator("#zim-status")).toContainText(/reinicie o programa/i);
});
