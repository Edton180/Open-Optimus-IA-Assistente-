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
        instalado: true, gerenciado: true, versao: "3.8.2", suportado: true, executando, arquivo: null, url: null,
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
  await expect(page.locator("#zim-kiwix-status")).toHaveText("Kiwix gerenciado");
  expect(erros).toEqual([]);
});


test("instalador e busca unificada têm ações reais e citações", async ({ page }) => {
  const erros = [];
  page.on("pageerror", (erro) => erros.push(erro.message));
  page.on("console", (msg) => { if (msg.type() === "error") erros.push(msg.text()); });
  let instalado = false;
  await page.route("**/api/zim", async (route) => route.fulfill({ json: {
    total: 1, tamanho_total_bytes: 1024, pasta_configurada: true,
    arquivos: [{ nome: "wikipedia_pt.zim", tamanho_bytes: 1024, modificado_em: 1795500000 }],
    kiwix: { instalado, gerenciado: instalado, suportado: true, versao: instalado ? "3.8.2" : null,
      executando: false, arquivo: null, url: null, host: "127.0.0.1", porta: 8767 }
  }}));
  await page.route("**/api/zim/instalar", async (route) => {
    instalado = true;
    await route.fulfill({ json: { instalado: true, gerenciado: true, versao: "3.8.2",
      mensagem: "Kiwix Tools instalado no diretório gerenciado do Optimus." } });
  });
  await page.route("**/api/zim/buscar?**", async (route) => route.fulfill({ json: {
    consulta: "segurança", total: 1, erros: [],
    resultados: [{ titulo: "Segurança", trecho: "Trecho do artigo", arquivo_zim: "wikipedia_pt.zim",
      citacao: "wikipedia_pt.zim · Segurança", tipo_fonte: "ZIM", url: "http://127.0.0.1:8767/content/wikipedia_pt/Seguranca" }]
  }}));
  await page.route("**/api/biblioteca?**", async (route) => route.fulfill({ json: {
    consulta: "segurança", total: 1,
    resultados: [{ titulo: "Manual interno", trecho: "Trecho do documento", fonte: "manual.pdf",
      citacao: "Manual interno — manual.pdf" }]
  }}));
  await page.goto("/");
  await page.locator('[data-tela="zim"]').click();
  await page.locator("#zim-instalar-kiwix").click();
  await expect(page.locator("#zim-kiwix-status")).toHaveText("Kiwix gerenciado");
  await expect(page.locator("#zim-instalacao-status")).toContainText("instalado");
  await page.locator("#zim-busca-termo").fill("segurança");
  await page.locator("#zim-busca-form button[type=submit]").click();
  await expect(page.locator("#zim-busca-resultados")).toContainText("Segurança");
  await expect(page.locator("#zim-busca-resultados")).toContainText("Manual interno");
  await expect(page.locator("#zim-busca-resultados")).toContainText("wikipedia_pt.zim");
  expect(erros).toEqual([]);
});
