const { test, expect } = require("@playwright/test");

test("painel Casa apresenta estado real e todos os controles chamam a API", async ({ page }) => {
  const acoes = [];
  await page.route("**/api/casa/gerenciado", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      acoes.push(body.acao);
      await route.fulfill({ status: 202, contentType: "application/json",
        body: JSON.stringify({ ok: true, estado: "executando" }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      runtime: { sistema: "Linux", suportado: true, docker_instalado: true,
        docker_ativo: true, docker_versao: "test", observacao: "" },
      container: { instalado: false, estado: "nao_instalado", rodando: false },
      tarefa: { estado: "concluido", mensagem: "Operação simulada com sucesso." },
      url: "", dados: "/tmp/optimus/home_assistant",
      nota: "Home Assistant Container de teste."
    }) });
  });

  await page.goto("/");
  await page.locator('[data-tela="casa"]').click();
  await expect(page.getByRole("heading", { name: "Casa inteligente" })).toBeVisible();
  await expect(page.locator("#ha-gerenciado")).toBeVisible();
  await expect(page.locator("#ha-gerenciado-badge")).toContainText("Pronto para instalar");
  await expect(page.locator("#ha-gerenciado-abrir")).toBeDisabled();

  await page.locator("#ha-gerenciado-atualizar").click();
  await page.locator("#ha-gerenciado-instalar").click();
  for (const acao of ["iniciar", "parar", "reiniciar", "atualizar", "backup"]) {
    await page.locator('[data-ha-acao="' + acao + '"]').click();
  }
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator('[data-ha-acao="desinstalar"]').click();

  await expect.poll(() => acoes).toEqual([
    "instalar", "iniciar", "parar", "reiniciar", "atualizar", "backup", "desinstalar"
  ]);
  await expect(page.locator("#ha-gerenciado-status")).toContainText("Operação simulada");
});

test("tela Casa explica os requisitos e limites do provisionamento", async ({ page }) => {
  await page.goto("/");
  await page.locator('[data-tela="casa"]').click();
  await expect(page.getByText(/Home Assistant Container/).first()).toBeVisible();
  await expect(page.getByText(/Supervisor|add-ons/).first()).toBeVisible();
  await expect(page.getByText(/primeira abertura|primeira.*conta/i).first()).toBeVisible();
});
