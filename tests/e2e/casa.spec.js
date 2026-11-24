const { test, expect } = require("@playwright/test");

test("painel Casa apresenta estado real e todos os controles chamam a API", async ({ page }) => {
  await page.addInitScript(() => {
    window.__haActions = [];
    const fetchOriginal = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      const raw = typeof input === "string" ? input : input.url;
      const url = new URL(raw, window.location.href);
      if (url.pathname === "/api/casa/gerenciado") {
        if ((init.method || "GET").toUpperCase() === "POST") {
          window.__haActions.push(JSON.parse(init.body || "{}").acao);
          return new Response(JSON.stringify({ ok: true, estado: "executando" }), {
            status: 202, headers: { "Content-Type": "application/json" }
          });
        }
        return new Response(JSON.stringify({
          runtime: { sistema: "Linux", suportado: true, docker_instalado: true,
            docker_ativo: true, docker_versao: "test", observacao: "" },
          container: { instalado: false, estado: "nao_instalado", rodando: false },
          tarefa: { estado: "concluido", mensagem: "Operação simulada com sucesso." },
          url: "", dados: "/tmp/optimus/home_assistant",
          nota: "Home Assistant Container de teste."
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return fetchOriginal(input, init);
    };
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

  await expect.poll(() => page.evaluate(() => window.__haActions)).toEqual([
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
