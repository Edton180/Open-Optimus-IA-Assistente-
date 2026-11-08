"""Internet: pesquisa, leitura de páginas, notícias e clima (sem chave de API)."""

from __future__ import annotations

import html
import re

import httpx

from optimus.tools.base import ferramenta, numero, texto

_AGENTE = {"User-Agent": "Mozilla/5.0 (Optimus assistente local)"}


def _buscador():
    from ddgs import DDGS

    return DDGS()


@ferramenta(
    "pesquisar_web",
    "Pesquisa na internet e devolve títulos, links e trechos. Use para fatos atuais, "
    "notícias, preços, documentação e qualquer coisa que você não saiba com certeza.",
    {"consulta": texto("O que pesquisar"),
     "quantidade": numero("Quantos resultados (1 a 10)")},
    grupo="internet", obrigatorios=["consulta"],
)
def pesquisar_web(ctx, consulta: str, quantidade: int = 0):
    limite = int(quantidade or ctx.config.get("internet", "max_resultados", 5))
    resultados = list(_buscador().text(consulta, region="br-pt", max_results=max(1, limite)))
    return {"consulta": consulta, "itens": [
        {"nome": r.get("title", ""), "link": r.get("href", ""), "trecho": r.get("body", "")}
        for r in resultados]}


@ferramenta(
    "noticias",
    "Busca notícias recentes sobre um assunto.",
    {"assunto": texto("Assunto das notícias")},
    grupo="internet",
)
def noticias(ctx, assunto: str):
    resultados = list(_buscador().news(assunto, region="br-pt", max_results=8))
    return {"assunto": assunto, "itens": [
        {"nome": r.get("title", ""), "link": r.get("url", ""), "fonte": r.get("source", ""),
         "data": r.get("date", ""), "trecho": r.get("body", "")} for r in resultados]}


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
