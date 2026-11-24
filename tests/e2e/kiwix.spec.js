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
      instalado: true, gerenciado: true, versao: "3.8.2", executando: true, arquivo: "wikipedia_pt.zim",
      url: "http://127.0.0.1:8767/", host: "127.0.0.1", porta: 8767
    }});
  });
  await page.route("**/api/zim/parar", async (route) => {
    executando = false;
    await route.fulfill({ json: {
      instalado: true, gerenciado: true, versao: "3.8.2", executando: false, arquivo: null, url: null,
      host: "127.0.0.1", porta: 8767
    }});
  });

  await page.goto("/");
  await page.locator('[data-tela="zim"]').click();
  await expect(page.locator("#zim-arquivo")).toContainText("wikipedia_pt.zim");
  await page.locator("#zim-arquivo").selectOption("wikipedia_pt.zim");
  await page.locator("#zim-abrir").click();
  await expect(page.locator("#zim-kiwix-status")).toHaveText("Leitor em execução");
  const linkLeitor = page.locator("#zim-leitor-link a");
  await expect(linkLeitor).toHaveAttribute("href", "/api/zim/leitor/");
  await expect(linkLeitor).toHaveAttribute("target", "_blank");
  // A nova guia deve permanecer no mesmo host do Optimus, nunca no localhost
  // do dispositivo que está lendo (que seria o celular no acesso remoto).
  await page.context().route("**/api/zim/leitor/", (route) => route.fulfill({
    status: 200, contentType: "text/html; charset=utf-8",
    body: "<!doctype html><html><body>Leitor ZIM</body></html>"
  }));
  const popupPromise = page.waitForEvent("popup");
  await linkLeitor.click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(/\/api\/zim\/leitor\/$/);
  await expect(popup.locator("body")).toContainText("Leitor ZIM");
  await popup.close();
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
  let indexado = false;
  await page.route("**/api/zim/status", async (route) => route.fulfill({ json: {
    artigos_indexados: indexado ? 1 : 0, trechos: indexado ? 2 : 0,
    com_embeddings: 0, arquivos: []
  }}));
  await page.route("**/api/zim/indexar", async (route) => {
    indexado = true;
    await route.fulfill({ json: { indexados: 1, artigos_processados: 1, trechos: 2,
      embeddings_atualizados: 0, erros: [], estado: { artigos_indexados: 1, trechos: 2 } } });
  });
  await page.route("**/api/zim/rag**", async (route) => route.fulfill({ json: {
    resultados: [{ titulo: "Segurança", trecho: "Trecho do artigo", arquivo: "wikipedia_pt.zim",
      artigo: "Seguranca", citacao: "Segurança — wikipedia_pt.zim#Seguranca",
      tipo_fonte: "ZIM", url: "zim://wikipedia_pt.zim/Seguranca" }]
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
  await page.locator("#zim-indexar").click();
  await expect(page.locator("#zim-index-status")).toContainText("1 artigos");
  expect(erros).toEqual([]);
});
