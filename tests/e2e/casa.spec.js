const { test, expect } = require("@playwright/test");

test("Casa inteligente usa API real do painel sem chamar instaladores no CI", async ({ page }) => {
  const erros = [];
  const acoes = [];
  page.on("pageerror", (erro) => erros.push(erro.message));
  page.on("console", (msg) => { if (msg.type() === "error") erros.push(msg.text()); });

  let container = { instalado: true, estado: "exited", rodando: false };
  let tarefa = { estado: "ocioso", mensagem: "", erro: "" };
  await page.route("**/api/casa/gerenciado", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: {
        runtime: { sistema: "Linux", suportado: true, docker_instalado: true,
          docker_ativo: true, docker_versao: "mock", observacao: "" },
        container, tarefa, url: container.rodando ? "http://127.0.0.1:8123" : "",
        nota: "Home Assistant Container"
      }});
    }
    const body = route.request().postDataJSON();
    acoes.push(body.acao);
    if (body.acao === "instalar" || body.acao === "iniciar" || body.acao === "reiniciar") {
      container = { instalado: true, estado: "running", rodando: true };
    } else if (body.acao === "parar" || body.acao === "desinstalar") {
      container = { instalado: body.acao !== "desinstalar", estado: "exited", rodando: false };
    }
    tarefa = { estado: "concluido", mensagem: "Operação simulada: " + body.acao,
      resultado: body.acao === "logs" ? { logs: "log de teste" } : {} };
    return route.fulfill({ status: 202, json: { ok: true, estado: "executando" } });
  });
  await page.route("**/api/casa/aparelhos", async (route) => route.fulfill({
    json: { ok: true, total: 2, aparelhos: [
      { entity_id: "light.sala", dominio: "light", nome: "Luz da sala", estado: "on", unidade: "", controlavel: true },
      { entity_id: "switch.tomada", dominio: "switch", nome: "Tomada", estado: "off", unidade: "", controlavel: true },
      { entity_id: "sensor.temperatura", dominio: "sensor", nome: "Temperatura", estado: "25", unidade: "°C", controlavel: false }
    ]}
  }));
  await page.route("**/api/casa/registro", async (route) => route.fulfill({
    json: {ok:true, dispositivos:[
      {id:"ha:light.sala", nome:"Luz da sala", integracao:"home_assistant",
       comodo:"Sala", disponibilidade:"online", confianca_estado:"confirmed"},
      {id:"ha:sensor.temperatura", nome:"Temperatura", integracao:"home_assistant",
       comodo:"", disponibilidade:"online", confianca_estado:"confirmed"}
    ]}
  }));
  await page.route("**/api/casa/registro-remover", async (route) =>
    route.fulfill({json:{ok:true}}));
  await page.route("**/api/casa/controle", async (route) => {
    const body = route.request().postDataJSON();
    acoes.push(body.servico + ":" + body.entity_id);
    return route.fulfill({ json: { ok: true }});
  });

  await page.goto("/");
  await page.locator('[data-tela="casa"]').click();
  await expect(page.getByRole("heading", { name: "Casa inteligente" })).toBeVisible();
  await expect(page.locator("#ha-gerenciado")).toBeVisible();
  await expect(page.locator("#ha-gerenciado-badge")).toContainText("Instalado / parado");
  await page.locator("#ha-gerenciado-atualizar").click();
  await page.locator("#ha-gerenciado-instalar").click();
  await expect(page.locator("#ha-gerenciado-abrir")).toBeEnabled();

  for (const acao of ["iniciar", "parar", "reiniciar", "atualizar", "backup", "logs"]) {
    await page.locator('[data-ha-acao="' + acao + '"]').click();
  }
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator('[data-ha-acao="desinstalar"]').click();
  await expect.poll(() => acoes).toContain("desinstalar");

  await page.locator("#casa-atualizar").click();
  await expect(page.locator("#casa-aparelhos")).toContainText("Luz da sala");
  await expect(page.locator("#casa-aparelhos")).toContainText("Temperatura");
  await expect(page.locator('[data-casa-controle="sensor.temperatura"]')).toHaveCount(0);
  await expect(page.locator("#casa-inventario")).toContainText("Luz da sala");
  await page.locator('[data-casa-controle="light.sala"]').click();
  await expect.poll(() => acoes).toContain("turn_off:light.sala");

  expect(erros).toEqual([]);
});

test("painel Casa informa quando o backend instalado está desatualizado", async ({ page }) => {
  await page.route("**/api/casa/gerenciado", (route) =>
    route.fulfill({ status: 404, contentType: "application/json",
      body: JSON.stringify({ erro: "rota não encontrada" }) }));
  await page.goto("/");
  await page.locator('[data-tela="casa"]').click();
  await expect(page.locator("#ha-gerenciado-diagnostico")).toContainText(/API desta instalação está desatualizada/i);
});

test("tela Casa explica o onboarding e preservação dos dados", async ({ page }) => {
  await page.goto("/");
  await page.locator('[data-tela="casa"]').click();
  await expect(page.getByText(/Home Assistant Container/).first()).toBeVisible();
  await expect(page.getByText(/primeira abertura|primeira.*conta/i).first()).toBeVisible();
  await expect(page.getByText(/preserva.*dados/i).first()).toBeVisible();
});
