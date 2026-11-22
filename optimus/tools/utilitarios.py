"""Utilitários do dia a dia: senha, sorteio, dias até uma data, câmbio, textos rápidos e notas.

Pedidos curtos que o assistente resolve na hora, como "gera uma senha de 20", "cara ou coroa",
"quantos dias faltam pro Natal?", "quanto está o dólar?", "copia meu pix" e "anota que preciso
comprar café". Tudo fica no PC (pasta do Optimus): textos rápidos em `textos_rapidos.json` e
notas como arquivos Markdown em `notas/`, fáceis de abrir em qualquer editor.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import secrets
import string
import unicodedata
from pathlib import Path

from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, numero, texto


def _base() -> Path:
    from optimus.config import pasta_base

    return pasta_base()


def _normal(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


# --------------------------------------------------------------------------- senha / sorteio
@ferramenta(
    "gerar_senha",
    "Gera uma senha forte e aleatória (gerador criptográfico do sistema). Não guarda a senha.",
    {"tamanho": numero("Quantidade de caracteres (padrão 16, de 6 a 128)"),
     "simbolos": {"type": "boolean", "description": "Usar símbolos (padrão sim)"},
     "copiar": {"type": "boolean", "description": "Copiar para a área de transferência"}},
    grupo="geral", risco=LIVRE, obrigatorios=[],
)
def gerar_senha(ctx, tamanho: int = 16, simbolos: bool = True, copiar: bool = False):
    tamanho = max(6, min(128, int(tamanho or 16)))
    grupos = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
    if simbolos:
        grupos.append("!@#$%&*-_=+?")
    todos = "".join(grupos)
    while True:  # garante pelo menos um de cada grupo
        senha = "".join(secrets.choice(todos) for _ in range(tamanho))
        if all(any(c in g for c in senha) for g in grupos):
            break
    saida = {"senha": senha, "tamanho": tamanho}
    if copiar:
        saida["copiada"] = _copiar(senha)
    return saida


@ferramenta(
    "sortear",
    "Sorteios rápidos: cara ou coroa, dado, número entre dois valores ou um item de uma lista.",
    {"tipo": {"type": "string", "enum": ["moeda", "dado", "numero", "lista"]},
     "minimo": numero("Para 'numero': menor valor (padrão 1)"),
     "maximo": numero("Para 'numero': maior valor; para 'dado': lados (padrão 6)"),
     "itens": texto("Para 'lista': itens separados por vírgula")},
    grupo="geral", risco=LIVRE, obrigatorios=["tipo"],
)
def sortear(ctx, tipo: str = "moeda", minimo: int = 1, maximo: int = 0, itens: str = ""):
    if tipo == "moeda":
        return {"resultado": secrets.choice(["cara", "coroa"])}
    if tipo == "dado":
        lados = max(2, int(maximo or 6))
        return {"resultado": secrets.randbelow(lados) + 1, "lados": lados}
    if tipo == "numero":
        a, b = int(minimo or 1), int(maximo or 100)
        a, b = min(a, b), max(a, b)
        return {"resultado": a + secrets.randbelow(b - a + 1), "entre": [a, b]}
    opcoes = [i.strip() for i in re.split(r"[,;\n]| ou ", itens or "") if i.strip()]
    if not opcoes:
        return {"erro": "Diga os itens separados por vírgula."}
    return {"resultado": secrets.choice(opcoes), "opcoes": opcoes}


# --------------------------------------------------------------------------- datas
def _pascoa(ano: int) -> dt.date:
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return dt.date(ano, mes, dia)


def _datas_fixas(ano: int) -> dict[str, dt.date]:
    pascoa = _pascoa(ano)
    return {
        "natal": dt.date(ano, 12, 25), "ano novo": dt.date(ano + 1, 1, 1),
        "reveillon": dt.date(ano, 12, 31), "pascoa": pascoa,
        "carnaval": pascoa - dt.timedelta(days=47), "dia das criancas": dt.date(ano, 10, 12),
        "dia dos namorados": dt.date(ano, 6, 12), "independencia": dt.date(ano, 9, 7),
        "tiradentes": dt.date(ano, 4, 21), "finados": dt.date(ano, 11, 2),
        "proclamacao da republica": dt.date(ano, 11, 15), "dia do trabalho": dt.date(ano, 5, 1),
    }


def interpretar_data(alvo: str, hoje: dt.date) -> dt.date | None:
    t = _normal(alvo)
    for nome in sorted(_datas_fixas(hoje.year), key=len, reverse=True):
        if nome in t:
            data = _datas_fixas(hoje.year)[nome]
            if data < hoje:
                data = _datas_fixas(hoje.year + 1)[nome]
            return data
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?", t)
    if m:
        dia, mes = int(m[1]), int(m[2])
        ano = int(m[3]) if m[3] else hoje.year
        if ano < 100:
            ano += 2000
        try:
            data = dt.date(ano, mes, dia)
        except ValueError:
            return None
        if not m[3] and data < hoje:
            data = data.replace(year=hoje.year + 1)
        return data
    return None


@ferramenta(
    "dias_ate",
    "Quantos dias faltam (ou passaram) até uma data: 'Natal', 'Carnaval', 'Páscoa', "
    "'ano novo', '25/12', '10/03/2027'...",
    {"data": texto("A data ou o nome da data comemorativa")},
    grupo="geral", risco=LIVRE,
)
def dias_ate(ctx, data: str, hoje: dt.date | None = None):
    hoje = hoje or dt.date.today()
    alvo = interpretar_data(data, hoje)
    if not alvo:
        return {"erro": f"Não entendi a data '{data}'. Use, por exemplo, 25/12 ou 'Natal'."}
    dias = (alvo - hoje).days
    semana = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][alvo.weekday()]
    if dias == 0:
        frase = "É hoje!"
    elif dias > 0:
        frase = f"Faltam {dias} dia{'s' if dias != 1 else ''}."
    else:
        frase = f"Já passaram {-dias} dia{'s' if dias != -1 else ''}."
    return {"data": alvo.strftime("%d/%m/%Y"), "dia_da_semana": semana, "dias": dias,
            "mensagem": f"{frase} ({alvo.strftime('%d/%m/%Y')}, {semana})"}


# --------------------------------------------------------------------------- câmbio
_MOEDAS = {"dolar": "USD", "dolar americano": "USD", "dollar": "USD", "euro": "EUR",
           "libra": "GBP", "libra esterlina": "GBP", "iene": "JPY", "yen": "JPY",
           "peso argentino": "ARS", "peso mexicano": "MXN", "peso chileno": "CLP",
           "peso colombiano": "COP", "peso uruguaio": "UYU", "guarani": "PYG",
           "dolar canadense": "CAD", "dolar australiano": "AUD", "franco suico": "CHF",
           "franco": "CHF", "yuan": "CNY", "renminbi": "CNY", "rupia": "INR", "rublo": "RUB",
           "bitcoin": "BTC", "ethereum": "ETH", "real": "BRL", "reais": "BRL"}
_ENCHIMENTO = r"^(?:o|a|os|as|do|da|de|em|para|pra|pro|no|na)\s+"


def _codigo(moeda: str) -> str | None:
    """Código ISO da moeda, ou None se o nome não for reconhecido (nunca chuta outra)."""
    t = re.sub(r"\s+", " ", _normal(moeda))
    t = re.sub(_ENCHIMENTO, "", t)
    if re.fullmatch(r"[a-z]{3}", t):
        return t.upper()
    return _MOEDAS.get(t) or _MOEDAS.get(t.rstrip("s"))


@ferramenta(
    "cotacao",
    "Cotação atual de uma moeda (dólar, euro, libra, bitcoin...) em reais ou em outra moeda, "
    "e conversão de um valor.",
    {"moeda": texto("Moeda, ex.: dólar, euro, BTC (padrão dólar)"),
     "para": texto("Moeda de destino (padrão real)"),
     "valor": {"type": "number", "description": "Valor a converter (opcional)"}},
    grupo="internet", risco=LIVRE, obrigatorios=[],
)
def cotacao(ctx, moeda: str = "dólar", para: str = "real", valor: float = 0, cliente=None):
    import httpx

    de, ate = _codigo(moeda or "dólar"), _codigo(para or "real")
    if not de or not ate:
        desconhecida = moeda if not de else para
        return {"erro": f"Não conheço a moeda '{desconhecida}'. Use o código de 3 letras "
                        "(ex.: AUD, MXN, CHF) ou o nome completo (ex.: peso mexicano)."}
    if de == ate:
        return {"erro": "As duas moedas são iguais."}
    par = f"{de}-{ate}"
    try:
        dono = cliente or httpx.Client(timeout=10)
        try:
            r = dono.get(f"https://economia.awesomeapi.com.br/json/last/{par}")
            r.raise_for_status()
            dado = r.json()[par.replace("-", "")]
        finally:
            if cliente is None:
                dono.close()
        preco = float(dado["bid"])
    except Exception as erro:  # noqa: BLE001 - rede, par inexistente...
        return {"erro": f"Não consegui a cotação {par} agora: {erro}"}
    saida = {"par": par, "cotacao": round(preco, 4), "variacao_pct": dado.get("pctChange"),
             "atualizado": dado.get("create_date"),
             "mensagem": f"1 {de} = {preco:,.2f} {ate}".replace(",", "X").replace(".", ",")
                         .replace("X", ".")}
    if valor:
        convertido = float(valor) * preco
        saida["convertido"] = round(convertido, 2)
        saida["mensagem"] += f"; {valor:g} {de} = {convertido:,.2f} {ate}".replace(
            ",", "X").replace(".", ",").replace("X", ".")
    return saida


# --------------------------------------------------------------------------- textos rápidos
def _copiar(conteudo: str) -> bool:
    try:
        import pyperclip

        pyperclip.copy(conteudo)
        return True
    except Exception:  # noqa: BLE001 - sem pyperclip ou sem área de transferência
        return False


def _arq_textos() -> Path:
    return _base() / "textos_rapidos.json"


def _ler_textos() -> dict[str, str]:
    try:
        return json.loads(_arq_textos().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_textos(dados: dict[str, str]) -> None:
    arq = _arq_textos()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def _achar_texto(dados: dict[str, str], nome: str) -> str | None:
    alvo = _normal(nome)
    alvo = re.sub(r"^(meu|minha|o|a)\s+", "", alvo)
    if alvo in dados:
        return alvo
    for chave in dados:
        if chave in alvo or alvo in chave:
            return chave
    return None


@ferramenta(
    "texto_rapido_salvar",
    "Guarda um texto que você usa sempre (chave pix, endereço, e-mail, assinatura) com um "
    "nome curto, para copiar depois com um pedido como 'copia meu pix'.",
    {"nome": texto("Nome curto, ex.: pix, endereço, assinatura"),
     "conteudo": texto("O texto a guardar")},
    grupo="produtividade", risco=LIVRE,
)
def texto_rapido_salvar(ctx, nome: str, conteudo: str):
    dados = _ler_textos()
    chave = re.sub(r"^(meu|minha|o|a)\s+", "", _normal(nome))
    dados[chave] = conteudo
    _gravar_textos(dados)
    return {"mensagem": f"Guardei '{chave}'. Diga 'copia meu {chave}' quando precisar."}


@ferramenta(
    "texto_rapido_copiar",
    "Copia para a área de transferência um texto rápido guardado (ex.: 'copia meu pix').",
    {"nome": texto("Nome do texto, ex.: pix")},
    grupo="produtividade", risco=LIVRE,
)
def texto_rapido_copiar(ctx, nome: str):
    dados = _ler_textos()
    chave = _achar_texto(dados, nome)
    if not chave:
        return {"erro": f"Não tenho um texto chamado '{nome}'.", "disponiveis": sorted(dados)}
    if _copiar(dados[chave]):
        return {"mensagem": f"Copiei seu {chave}. É só colar."}
    return {"mensagem": f"Não consegui usar a área de transferência. Seu {chave}:",
            "conteudo": dados[chave]}


@ferramenta(
    "textos_rapidos_listar", "Lista os nomes dos textos rápidos guardados.",
    {}, grupo="produtividade", risco=LIVRE,
)
def textos_rapidos_listar(ctx):
    return {"textos": sorted(_ler_textos())}


@ferramenta(
    "texto_rapido_apagar", "Apaga um texto rápido guardado.",
    {"nome": texto("Nome do texto")}, grupo="produtividade", risco=MODERADO,
)
def texto_rapido_apagar(ctx, nome: str):
    dados = _ler_textos()
    chave = _achar_texto(dados, nome)
    if not chave:
        return {"erro": f"Não tenho um texto chamado '{nome}'."}
    dados.pop(chave)
    _gravar_textos(dados)
    return {"mensagem": f"Apaguei '{chave}'."}


# --------------------------------------------------------------------------- notas
def _pasta_notas() -> Path:
    pasta = _base() / "notas"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _slug(t: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", _normal(t)).strip("-")
    return s[:60] or "nota"


@ferramenta(
    "nota_criar",
    "Anota algo num caderno de notas (arquivo Markdown no PC). Se já existir uma nota com o "
    "mesmo título, acrescenta no fim. Ex.: 'anota que preciso comprar café'.",
    {"texto": texto("O que anotar"),
     "titulo": texto("Título da nota (padrão: 'Anotações')")},
    grupo="produtividade", risco=LIVRE, obrigatorios=["texto"],
)
def nota_criar(ctx, texto: str, titulo: str = ""):
    titulo = (titulo or "Anotações").strip()
    arq = _pasta_notas() / f"{_slug(titulo)}.md"
    agora = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    novo = not arq.exists()
    with open(arq, "a", encoding="utf-8") as f:
        if novo:
            f.write(f"# {titulo}\n\n")
        f.write(f"- {texto.strip()}  _({agora})_\n")
    return {"mensagem": f"Anotado em '{titulo}'.", "arquivo": str(arq)}


@ferramenta(
    "notas_listar", "Lista as notas do caderno, com a quantidade de itens de cada uma.",
    {}, grupo="produtividade", risco=LIVRE,
)
def notas_listar(ctx):
    saida = []
    for arq in sorted(_pasta_notas().glob("*.md")):
        linhas = arq.read_text(encoding="utf-8").splitlines()
        titulo = linhas[0].lstrip("# ").strip() if linhas else arq.stem
        saida.append({"titulo": titulo, "itens": sum(1 for x in linhas if x.startswith("- "))})
    return {"notas": saida}


@ferramenta(
    "nota_ler", "Lê uma nota do caderno pelo título.",
    {"titulo": texto("Título da nota (padrão: 'Anotações')")},
    grupo="produtividade", risco=LIVRE, obrigatorios=[],
)
def nota_ler(ctx, titulo: str = ""):
    arq = _pasta_notas() / f"{_slug(titulo or 'Anotações')}.md"
    if not arq.exists():
        return {"erro": f"Não achei a nota '{titulo}'.",
                "notas": [n["titulo"] for n in notas_listar(ctx)["notas"]]}
    return {"titulo": titulo or "Anotações", "conteudo": arq.read_text(encoding="utf-8")[:8000]}


@ferramenta(
    "notas_buscar", "Procura uma palavra em todas as notas do caderno.",
    {"termo": texto("O que procurar")}, grupo="produtividade", risco=LIVRE,
)
def notas_buscar(ctx, termo: str):
    alvo = _normal(termo)
    achados = []
    for arq in sorted(_pasta_notas().glob("*.md")):
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if alvo and alvo in _normal(linha) and not linha.startswith("# "):
                achados.append({"nota": arq.stem, "linha": linha.strip()})
    return {"achados": achados[:50]}


@ferramenta(
    "nota_apagar", "Apaga uma nota inteira do caderno.",
    {"titulo": texto("Título da nota")}, grupo="produtividade", risco=MODERADO,
)
def nota_apagar(ctx, titulo: str):
    arq = _pasta_notas() / f"{_slug(titulo)}.md"
    if not arq.exists():
        return {"erro": f"Não achei a nota '{titulo}'."}
    arq.unlink()
    return {"mensagem": f"Apaguei a nota '{titulo}'."}


# --------------------------------------------------------------------------- modo só executar
@ferramenta(
    "modo_so_executar",
    "Liga ou desliga o modo 'só executar': o Optimus faz o que foi pedido e fica quieto, sem "
    "falar as respostas em voz alta (confirmações de segurança continuam).",
    {"ligar": {"type": "boolean", "description": "true liga, false desliga"}},
    grupo="geral", risco=LIVRE,
)
def modo_so_executar(ctx, ligar: bool = True):
    if not ctx or not getattr(ctx, "config", None):
        return {"erro": "Sem configuração."}
    ctx.config.definir("voz", "so_executar", bool(ligar))
    if getattr(ctx.config, "caminho", None):
        ctx.config.salvar()
    return {"mensagem": "Modo só executar ligado: faço e fico quieto." if ligar
            else "Modo só executar desligado: volto a falar as respostas."}
