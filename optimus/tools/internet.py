"""Internet: pesquisa, leitura de páginas, notícias e clima (sem chave de API)."""

from __future__ import annotations

import base64
import html
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

import httpx

from optimus.tools.base import ferramenta, numero, texto

_AGENTE = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like "
                     "Gecko) Chrome/130.0 Safari/537.36",
           "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"}


def _limpo(texto: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", texto or "")).strip()


def _ddgs(consulta: str, limite: int) -> list[dict]:
    from ddgs import DDGS

    # Timeout explícito: o primeiro provedor não pode prender a conversa por minutos.
    with DDGS(timeout=8) as ddgs:
        resultados = ddgs.text(consulta, region="br-pt", max_results=limite)
        return [{"nome": r.get("title", ""), "link": r.get("href", ""),
                 "trecho": r.get("body", "")} for r in resultados]


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


def _desembrulhar_url_busca(url: str) -> str:
    """Converte links de redirecionamento do Bing no endereço real do resultado."""
    try:
        partes = urlsplit(url)
        if "bing.com" not in partes.netloc.lower():
            return url
        valores = parse_qs(partes.query)
        destino = (valores.get("url") or valores.get("u") or [""])[0]
        destino = unquote(destino)
        if destino.startswith("a1"):
            codificado = destino[2:]
            try:
                destino = base64.urlsafe_b64decode(
                    codificado + "=" * (-len(codificado) % 4)).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return url
        return destino if destino.startswith(("http://", "https://")) else url
    except (ValueError, TypeError):
        return url


def ler_bing_html(pagina: str, limite: int = 8) -> list[dict]:
    itens = []
    for bloco in re.findall(r'(?s)<li class="b_algo".*?</li>', pagina):
        link = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', bloco, re.S)
        trecho = re.search(r"<p[^>]*>(.*?)</p>", bloco, re.S)
        if link:
            destino = _desembrulhar_url_busca(html.unescape(link.group(1)))
            itens.append({"nome": _limpo(link.group(2)), "link": destino,
                          "trecho": _limpo(trecho.group(1)) if trecho else ""})
        if len(itens) >= limite:
            break
    return itens


def _duckduckgo_html(consulta: str, limite: int) -> list[dict]:
    r = httpx.post("https://html.duckduckgo.com/html/", data={"q": consulta, "kl": "br-pt"},
                   headers=_AGENTE, timeout=8, follow_redirects=True)
    r.raise_for_status()
    return ler_duckduckgo_html(r.text, limite)


def _bing_html(consulta: str, limite: int) -> list[dict]:
    r = httpx.get("https://www.bing.com/search", params={"q": consulta, "setlang": "pt-BR",
                                                          "cc": "BR"},
                  headers=_AGENTE, timeout=8, follow_redirects=True)
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

_STOPWORDS = {
    "a", "à", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "é", "essa", "esse", "esta", "este", "hoje", "me", "na", "nas",
    "no", "nos", "o", "os", "ou", "para", "pela", "pelas", "pelo", "pelos",
    "por", "qual", "quais", "que", "se", "sobre", "um", "uma", "umas", "uns",
    "valor", "preço", "preco", "cotação", "cotacao", "atual", "agora",
}
_ALIAS = {
    "brb": {"banco", "brasilia", "bsli3", "bsli4"},
    "banco": {"brb", "brasilia"},
    "bsli3": {"brb", "banco", "brasilia"},
    "bsli4": {"brb", "banco", "brasilia"},
}


def _normalizar_busca(valor: str) -> str:
    valor = unicodedata.normalize("NFKD", valor or "")
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", valor.lower()).strip()


def _termos_busca(valor: str) -> set[str]:
    return {t for t in _normalizar_busca(valor).split()
            if len(t) > 1 and t not in _STOPWORDS}


def _variantes_consulta(consulta: str) -> list[str]:
    """Expande siglas conhecidas sem substituir nem perder a consulta original."""
    variantes = [consulta.strip()]
    normal = _normalizar_busca(consulta)
    if re.search(r"\bbrb\b", normal) and re.search(
            r"\b(acao|acoes|cotacao|bolsa|ticker|b3|papel|preco)\b", normal):
        variantes.append("BRB Banco de Brasília BSLI3 BSLI4 ações cotação B3")
    return list(dict.fromkeys(v for v in variantes if v))


def _pontuar_resultado(item: dict, variantes: list[str]) -> float:
    titulo = _termos_busca(item.get("nome", ""))
    trecho = _termos_busca(item.get("trecho", ""))
    if not titulo and not trecho:
        return 0.0
    melhor = 0.0
    for variante in variantes:
        termos = _termos_busca(variante)
        expandidos = set(termos)
        for termo in tuple(termos):
            expandidos.update(_ALIAS.get(termo, ()))
        if not expandidos:
            continue
        no_titulo = len(titulo & expandidos)
        no_texto = len(trecho & expandidos)
        cobertura = len((titulo | trecho) & expandidos) / len(expandidos)
        # Título pesa mais que snippet: coincidência no corpo não mascara outro assunto.
        score = min(1.0, cobertura * 0.65 + min(no_titulo, 3) * 0.12
                    + min(no_texto, 3) * 0.025)
        frase = _normalizar_busca(variante)
        titulo_normal = _normalizar_busca(item.get("nome", ""))
        if len(frase) > 7 and frase in titulo_normal:
            score += 0.18
        melhor = max(melhor, min(1.0, score))
    link = (item.get("link") or "").lower()
    if any(d in link for d in ("brb.com.br", "b3.com.br", "bcb.gov.br", "gov.br")):
        melhor = min(1.0, melhor + 0.08)
    return round(melhor, 3)


def _url_canonica(url: str) -> str:
    try:
        partes = urlsplit(url)
        query = "&".join(p for p in partes.query.split("&")
                         if p and not p.lower().startswith(
                             ("utm_", "gclid=", "fbclid=", "msclkid=")))
        return urlunsplit((partes.scheme.lower(), partes.netloc.lower(),
                           partes.path.rstrip("/"), query, ""))
    except ValueError:
        return url


@ferramenta(
    "pesquisar_web",
    "Pesquisa na internet, combina buscadores, filtra resultados fora do assunto e prioriza "
    "fontes relevantes. Para fatos atuais, notícias, preços e documentação. Confira os links "
    "antes de afirmar algo; se os resultados não corresponderem à pergunta, informe que não "
    "encontrou fontes adequadas em vez de inventar ou usar resultados irrelevantes.",
    {"consulta": texto("O que pesquisar"),
     "quantidade": numero("Quantos resultados (1 a 10)")},
    grupo="internet", obrigatorios=["consulta"],
)
def pesquisar_web(ctx, consulta: str, quantidade: int = 0):
    """Combina provedores, classifica relevância e evita retornar lixo fora do assunto."""
    limite = max(1, min(10, int(quantidade or ctx.config.get("internet", "max_resultados", 5))))
    variantes = _variantes_consulta(consulta)
    coletados: dict[str, dict] = {}
    provedores = []
    falhas = []
    for nome, buscar in BUSCADORES:
        if nome == "Wikipédia" and not re.search(
                r"\b(historia|biografia|conceito|o que e|quem foi|como funciona)\b",
                _normalizar_busca(consulta)):
            continue
        try:
            itens = buscar(variantes[0], min(10, max(limite, 6)))
            provedores.append(nome)
            for item in itens:
                link = item.get("link", "")
                if not link.startswith(("http://", "https://")):
                    continue
                chave = _url_canonica(link)
                if not chave:
                    continue
                existente = coletados.get(chave)
                novo = {**item, "provedor": nome, "link": link}
                if existente:
                    novo["provedores"] = sorted(set(
                        existente.get("provedores", [existente["provedor"]]) + [nome]))
                    if len(novo.get("trecho", "")) > len(existente.get("trecho", "")):
                        coletados[chave] = novo
                    else:
                        existente["provedores"] = novo["provedores"]
                else:
                    coletados[chave] = novo
        except Exception as erro:  # noqa: BLE001 - provedores externos variam
            falhas.append(f"{nome}: {type(erro).__name__}: {str(erro)[:100]}")

    def relevantes():
        saida = []
        for item in coletados.values():
            score = _pontuar_resultado(item, variantes)
            if score >= 0.16:
                saida.append({**item, "relevancia": score})
        saida.sort(key=lambda i: (i["relevancia"], len(i.get("trecho", ""))), reverse=True)
        return saida

    pontuados = relevantes()
    # Se a busca exata não trouxe material útil, tenta a expansão semântica da sigla.
    if len(pontuados) < min(3, limite) and len(variantes) > 1:
        for nome, buscar in BUSCADORES[:3]:
            try:
                itens = buscar(variantes[1], min(10, max(limite, 6)))
                if nome not in provedores:
                    provedores.append(nome)
                for item in itens:
                    link = item.get("link", "")
                    if not link.startswith(("http://", "https://")):
                        continue
                    chave = _url_canonica(link)
                    if chave and chave not in coletados:
                        coletados[chave] = {**item, "provedor": nome, "link": link}
            except Exception as erro:  # noqa: BLE001
                falhas.append(f"{nome} (consulta ampliada): {type(erro).__name__}: {str(erro)[:100]}")
        pontuados = relevantes()

    if not pontuados:
        return {"consulta": consulta, "erro": "Os buscadores não retornaram resultados "
                "com relação suficiente com a pergunta. Não use resultados genéricos como resposta.",
                "provedores_consultados": provedores, "falhas": falhas[:4]}
    origem = pontuados[0].get("provedor", "") if pontuados else ""
    return {"consulta": consulta, "buscador": origem, "consultas_usadas": variantes,
            "provedores_consultados": provedores, "total_relevantes": len(pontuados),
            "itens": pontuados[:limite]}


@ferramenta(
    "pesquisar_x",
    "Pesquisa publicações públicas recentes no X (Twitter) em tempo real. Requer um Bearer "
    "Token da API oficial do X configurado em provedores.x_api_chave. Use para tendências, "
    "declarações públicas e reações; diferencie posts de fatos confirmados.",
    {"consulta": texto("Termos da pesquisa no X"),
     "quantidade": numero("Quantidade de posts (1 a 10)")},
    grupo="internet", obrigatorios=["consulta"],
)
def pesquisar_x(ctx, consulta: str, quantidade: int = 0):
    token = ctx.config.get("provedores", "x_api_chave", "") or ""
    if not token:
        return {"erro": "A pesquisa no X exige um Bearer Token da API oficial. Configure "
                "provedores.x_api_chave no cofre do Optimus; a pesquisa web comum continua disponível."}
    limite = max(1, min(10, int(quantidade or 10)))
    try:
        resposta = httpx.get(
            "https://api.x.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {token}", **_AGENTE},
            params={"query": f"({consulta}) -is:retweet", "max_results": max(10, limite),
                    "tweet.fields": "created_at,public_metrics,lang,author_id",
                    "expansions": "author_id", "user.fields": "name,username,verified"},
            timeout=10,
        )
        if resposta.status_code in (401, 403):
            return {"erro": "A API do X recusou o token ou não liberou a pesquisa recente. "
                    "Verifique as permissões e o plano do projeto no portal de desenvolvedores."}
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError) as erro:
        return {"erro": f"Não consegui consultar a API do X: {type(erro).__name__}: {erro}"}
    usuarios = {u["id"]: u for u in dados.get("includes", {}).get("users", [])}
    itens = []
    for post in dados.get("data", [])[:limite]:
        autor = usuarios.get(post.get("author_id"), {})
        username = autor.get("username", "")
        itens.append({
            "autor": autor.get("name", ""),
            "usuario": "@" + username if username else "",
            "verificado": bool(autor.get("verified", False)),
            "texto": post.get("text", ""),
            "data": post.get("created_at", ""),
            "metricas": post.get("public_metrics", {}),
            "link": f"https://x.com/{username}/status/{post['id']}" if username else "",
        })
    return {"consulta": consulta, "fonte": "API oficial do X",
            "total": len(itens), "itens": itens}


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
                      headers=_AGENTE, timeout=8, follow_redirects=True)
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
