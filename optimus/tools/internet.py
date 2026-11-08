"""Internet: pesquisa, leitura de páginas, notícias e clima (sem chave de API)."""

from __future__ import annotations

import html
import re

import httpx

from optimus.tools.base import ferramenta, numero, texto

_AGENTE = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like "
                     "Gecko) Chrome/130.0 Safari/537.36",
           "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"}


def _limpo(texto: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", texto or "")).strip()


def _ddgs(consulta: str, limite: int) -> list[dict]:
    from ddgs import DDGS

    return [{"nome": r.get("title", ""), "link": r.get("href", ""), "trecho": r.get("body", "")}
            for r in DDGS().text(consulta, region="br-pt", max_results=limite)]


def ler_duckduckgo_html(pagina: str, limite: int = 8) -> list[dict]:
    itens = []
    for bloco in re.findall(r'(?s)<div class="result results_links.*?</div>\s*</div>', pagina):
        # Atributos em qualquer ordem: o DuckDuckGo muda o HTML de vez em quando.
        link = re.search(r'<a([^>]*\bclass="result__a"[^>]*)>(.*?)</a>', bloco, re.S)
        trecho = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', bloco, re.S)
        endereco = re.search(r'\bhref="([^"]+)"', link.group(1)) if link else None
        if not link or not endereco:
            continue
        href = html.unescape(endereco.group(1))
        destino = re.search(r"uddg=([^&]+)", href)
        if destino:
            from urllib.parse import unquote

            href = unquote(destino.group(1))
        itens.append({"nome": _limpo(link.group(2)), "link": href,
                      "trecho": _limpo(trecho.group(1)) if trecho else ""})
        if len(itens) >= limite:
            break
    return itens


def ler_bing_html(pagina: str, limite: int = 8) -> list[dict]:
    itens = []
    for bloco in re.findall(r'(?s)<li class="b_algo".*?</li>', pagina):
        link = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', bloco, re.S)
        trecho = re.search(r"<p[^>]*>(.*?)</p>", bloco, re.S)
        if link:
            itens.append({"nome": _limpo(link.group(2)), "link": html.unescape(link.group(1)),
                          "trecho": _limpo(trecho.group(1)) if trecho else ""})
        if len(itens) >= limite:
            break
    return itens


def _duckduckgo_html(consulta: str, limite: int) -> list[dict]:
    r = httpx.post("https://html.duckduckgo.com/html/", data={"q": consulta, "kl": "br-pt"},
                   headers=_AGENTE, timeout=15, follow_redirects=True)
    r.raise_for_status()
    return ler_duckduckgo_html(r.text, limite)


def _bing_html(consulta: str, limite: int) -> list[dict]:
    r = httpx.get("https://www.bing.com/search", params={"q": consulta, "setlang": "pt-BR",
                                                          "cc": "BR"},
                  headers=_AGENTE, timeout=15, follow_redirects=True)
    r.raise_for_status()
    return ler_bing_html(r.text, limite)


def _wikipedia(consulta: str, limite: int) -> list[dict]:
    r = httpx.get("https://pt.wikipedia.org/w/api.php", headers=_AGENTE, timeout=15, params={
        "action": "query", "list": "search", "srsearch": consulta, "format": "json",
        "srlimit": limite})
    r.raise_for_status()
    return [{"nome": i["title"], "trecho": _limpo(i.get("snippet", "")),
             "link": "https://pt.wikipedia.org/wiki/" + i["title"].replace(" ", "_")}
            for i in r.json().get("query", {}).get("search", [])]


BUSCADORES = [("DuckDuckGo", _ddgs), ("DuckDuckGo (html)", _duckduckgo_html),
              ("Bing", _bing_html), ("Wikipédia", _wikipedia)]


@ferramenta(
    "pesquisar_web",
    "Pesquisa na internet e devolve títulos, links e trechos. Use para fatos atuais, "
    "notícias, preços, documentação e qualquer coisa que você não saiba com certeza.",
    {"consulta": texto("O que pesquisar"),
     "quantidade": numero("Quantos resultados (1 a 10)")},
    grupo="internet", obrigatorios=["consulta"],
)
def pesquisar_web(ctx, consulta: str, quantidade: int = 0):
    """Tenta vários buscadores: se um bloquear ou cair, usa o próximo."""
    limite = max(1, min(10, int(quantidade or ctx.config.get("internet", "max_resultados", 5))))
    falhas = []
    for nome, buscar in BUSCADORES:
        try:
            itens = buscar(consulta, limite)
        except Exception as erro:  # noqa: BLE001 - cada buscador falha de um jeito
            falhas.append(f"{nome}: {type(erro).__name__}: {str(erro)[:120]}")
            continue
        if itens:
            return {"consulta": consulta, "buscador": nome, "itens": itens[:limite]}
        falhas.append(f"{nome}: sem resultados")
    return {"erro": "Não consegui pesquisar. Confira a conexão com a internet. Detalhes: " +
                    " | ".join(falhas)}


def ler_rss(conteudo: str, limite: int = 10) -> list[dict]:
    itens = []
    for bloco in re.findall(r"(?s)<item>(.*?)</item>", conteudo)[:limite]:
        def campo(nome, bloco=bloco):
            achado = re.search(rf"(?s)<{nome}[^>]*>(.*?)</{nome}>", bloco)
            valor = achado.group(1) if achado else ""
            valor = re.sub(r"^<!\[CDATA\[|\]\]>$", "", valor.strip())
            return _limpo(valor)
        itens.append({"nome": campo("title"), "link": campo("link"), "fonte": campo("source"),
                      "data": campo("pubDate")})
    return itens


@ferramenta(
    "noticias",
    "Busca notícias recentes sobre um assunto (Google Notícias, em português).",
    {"assunto": texto("Assunto das notícias")},
    grupo="internet",
)
def noticias(ctx, assunto: str):
    falhas = []
    try:
        url = "https://news.google.com/rss/search" if assunto else "https://news.google.com/rss"
        r = httpx.get(url, params={"q": assunto, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
                      headers=_AGENTE, timeout=15, follow_redirects=True)
        r.raise_for_status()
        itens = ler_rss(r.text, 8)
        if itens:
            return {"assunto": assunto, "fonte": "Google Notícias", "itens": itens}
    except httpx.HTTPError as erro:
        falhas.append(f"Google Notícias: {erro}")
    try:
        from ddgs import DDGS

        resultados = list(DDGS().news(assunto or "Brasil", region="br-pt", max_results=8))
        return {"assunto": assunto, "fonte": "DuckDuckGo", "itens": [
            {"nome": r.get("title", ""), "link": r.get("url", ""), "fonte": r.get("source", ""),
             "data": r.get("date", ""), "trecho": r.get("body", "")} for r in resultados]}
    except Exception as erro:  # noqa: BLE001
        falhas.append(f"DuckDuckGo: {erro}")
    return {"erro": "Não consegui buscar notícias. Detalhes: " + " | ".join(falhas)}


def html_para_texto(conteudo: str, limite: int = 8000) -> str:
    conteudo = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ",
                      conteudo)
    conteudo = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", conteudo)
    conteudo = re.sub(r"<[^>]+>", " ", conteudo)
    conteudo = html.unescape(conteudo)
    conteudo = re.sub(r"[ \t\r\f\v]+", " ", conteudo)
    conteudo = re.sub(r"\n\s*\n+", "\n\n", conteudo).strip()
    return conteudo[:limite]


@ferramenta(
    "ler_pagina",
    "Abre um link e devolve o texto da página (para ler artigos, documentação etc.).",
    {"url": texto("Endereço completo, com https://")},
    grupo="internet",
)
def ler_pagina(ctx, url: str):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    resposta = httpx.get(url, headers=_AGENTE, timeout=20, follow_redirects=True)
    resposta.raise_for_status()
    titulo = re.search(r"(?is)<title[^>]*>(.*?)</title>", resposta.text)
    return {"url": str(resposta.url),
            "titulo": html.unescape(titulo.group(1).strip()) if titulo else "",
            "texto": html_para_texto(resposta.text)}


@ferramenta(
    "clima",
    "Previsão do tempo atual e dos próximos dias para uma cidade.",
    {"cidade": texto("Nome da cidade")},
    grupo="internet",
)
def clima(ctx, cidade: str):
    geo = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": cidade, "count": 1, "language": "pt"}, timeout=15).json()
    if not geo.get("results"):
        return {"erro": f"Não achei a cidade {cidade}"}
    lugar = geo["results"][0]
    tempo = httpx.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lugar["latitude"], "longitude": lugar["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 3}, timeout=15).json()
    return {"cidade": f"{lugar['name']}, {lugar.get('admin1', '')}", "agora": tempo.get("current"),
            "proximos_dias": tempo.get("daily")}
