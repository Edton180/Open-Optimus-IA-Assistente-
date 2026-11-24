const { test, expect } = require("@playwright/test");

test("controles Kiwix iniciam e encerram leitor local", async ({ page }) => {
  const erros = [];
  page.on("pageerror", (erro) => erros.push(erro.message));
  page.on("console", (msg) => { if (msg.type() === "error") erros.push(msg.text()); });

  let executando = false;
  await page.route("**/api/zim", async (route) => route.fulfill({
    json: {
      total: 1,
      tamanho_total_bytes: 1024,
      pasta_configurada: true,
      arquivos: [{ nome: "wikipedia_pt.zim", tamanho_bytes: 1024, modificado_em: 1795500000 }],
      kiwix: {
        instalado: true, executando, arquivo: null, url: null,
        host: "127.0.0.1", porta: 8767
      }
    }
  }));
  await page.route("**/api/zim/iniciar", async (route) => {
    executando = true;
    await route.fulfill({ json: {
      instalado: true, executando: true, arquivo: "wikipedia_pt.zim",
      url: "http://127.0.0.1:8767/", host: "127.0.0.1", porta: 8767
    }});
  });
  await page.route("**/api/zim/parar", async (route) => {
    executando = false;
    await route.fulfill({ json: {
      instalado: true, executando: false, arquivo: null, url: null,
      host: "127.0.0.1", porta: 8767
    }});
  });

  await page.goto("/");
  await page.locator('[data-tela="zim"]').click();
  await expect(page.locator("#zim-arquivo")).toContainText("wikipedia_pt.zim");
  await page.locator("#zim-arquivo").selectOption("wikipedia_pt.zim");
  await page.locator("#zim-abrir").click();
  await expect(page.locator("#zim-kiwix-status")).toHaveText("Leitor em execução");
  await expect(page.locator("#zim-leitor-link a")).toHaveAttribute("href", "http://127.0.0.1:8767/");
  await page.locator("#zim-fechar").click();
  await expect(page.locator("#zim-kiwix-status")).toHaveText("Kiwix instalado");
  expect(erros).toEqual([]);
});
