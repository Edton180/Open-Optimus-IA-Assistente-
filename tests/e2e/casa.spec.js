const { test, expect } = require("@playwright/test");

test("painel Casa apresenta estado real e todos os controles chamam a API", async ({ page }) => {
  const errosPagina = [];
  page.on("pageerror", (erro) => errosPagina.push(erro.message));
  page.on("console", (msg) => { if (msg.type() === "error") errosPagina.push(msg.text()); });
  await page.goto("/");
  await page.locator('[data-tela="casa"]').click();
  await expect(page.getByRole("heading", { name: "Casa inteligente" })).toBeVisible();
  await expect(page.locator("#ha-gerenciado")).toBeVisible();
  await expect(page.locator("#ha-gerenciado-badge")).toContainText("Pronto para instalar");
  await expect(page.locator("#ha-gerenciado-abrir")).toBeDisabled();

  await page.locator("#ha-gerenciado-atualizar").click();
  await page.locator("#ha-gerenciado-instalar").click();
  for (const acao of ["iniciar", "parar", "reiniciar", "atualizar", "backup", "logs"]) {
    await page.locator('[data-ha-acao="' + acao + '"]').click();
  }
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator('[data-ha-acao="desinstalar"]').click();

  await expect.poll(async () => {
    const respostaAcoes = await page.request.get("/api/casa/gerenciado");
    return (await respostaAcoes.json()).acoes;
  }).toEqual([
    "instalar", "iniciar", "parar", "reiniciar", "atualizar", "backup", "logs", "desinstalar"
  ]);
  await expect(page.locator("#ha-gerenciado-status")).toContainText("Operação simulada");
  expect(errosPagina).toEqual([]);
});

test("tela Casa explica os requisitos e limites do provisionamento", async ({ page }) => {
  await page.goto("/");
  await page.locator('[data-tela="casa"]').click();
  await expect(page.getByText(/Home Assistant Container/).first()).toBeVisible();
  await expect(page.getByText(/Supervisor|add-ons/).first()).toBeVisible();
  await expect(page.getByText(/primeira abertura|primeira.*conta/i).first()).toBeVisible();
});
