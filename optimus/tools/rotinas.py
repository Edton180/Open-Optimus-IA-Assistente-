"""Rotinas: sequências de passos que você dispara por um nome (aba Rotinas do painel).

Uma rotina é uma lista de passos em ordem — cada passo é um pedido em texto, como você
falaria com o Optimus (ex.: "bom dia" → "me dê o resumo do dia", "toque minha playlist",
"qual a previsão do tempo"). Tudo guardado no banco local, no PC do usuário. Executar devolve
os passos em ordem para a interface/voz rodarem um a um.
"""

from __future__ import annotations

from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, numero, texto


def _sem_banco(ctx) -> bool:
    return not ctx or not getattr(ctx, "banco", None)


def _passos(passos) -> list[str]:
    """Aceita lista de passos ou um texto com um passo por linha (ou separado por ';')."""
    if isinstance(passos, str):
        bruto = passos.replace(";", "\n").splitlines()
    elif isinstance(passos, (list, tuple)):
        bruto = passos
    else:
        bruto = []
    return [str(p).strip() for p in bruto if str(p).strip()]


@ferramenta(
    "rotina_criar",
    "Cria (ou regrava, se já existir pelo mesmo nome) uma rotina: um nome e uma lista de "
    "passos em ordem. Cada passo é um pedido em texto, como você falaria com o Optimus.",
    {"nome": texto("Nome da rotina (ex.: 'bom dia')"),
     "passos": {"type": "array", "items": {"type": "string"},
                "description": "Passos em ordem, cada um um pedido em texto"}},
    grupo="produtividade", risco=LIVRE, obrigatorios=["nome", "passos"],
)
def rotina_criar(ctx, nome: str, passos=None):
    if _sem_banco(ctx):
        return {"erro": "Sem banco para guardar a rotina."}
    lista = _passos(passos)
    if not lista:
        return {"erro": "A rotina precisa de pelo menos um passo."}
    rid = ctx.banco.criar_rotina(nome, lista)
    return {"id": rid, "mensagem": f"Rotina '{nome.strip()}' criada com {len(lista)} passo(s).",
            "passos": lista}


@ferramenta(
    "rotinas_listar",
    "Lista as rotinas com os seus passos.",
    {}, grupo="produtividade", risco=LIVRE,
)
def rotinas_listar(ctx):
    if _sem_banco(ctx):
        return {"rotinas": []}
    return {"rotinas": ctx.banco.listar_rotinas()}


@ferramenta(
    "rotina_executar",
    "Devolve os passos de uma rotina, em ordem, para a interface/voz rodarem um a um. "
    "Procure pela rotina pelo nome.",
    {"nome": texto("Nome da rotina a executar")},
    grupo="produtividade", risco=LIVRE, obrigatorios=["nome"],
)
def rotina_executar(ctx, nome: str):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    rotina = ctx.banco.rotina_por_nome(nome)
    if not rotina:
        return {"erro": f"Não achei a rotina '{nome.strip()}'."}
    if not rotina["passos"]:
        return {"erro": f"A rotina '{rotina['nome']}' não tem passos."}
    return {"nome": rotina["nome"], "passos": rotina["passos"],
            "mensagem": f"Rodando a rotina '{rotina['nome']}' ({len(rotina['passos'])} passos)."}


@ferramenta(
    "rotina_apagar",
    "Apaga uma rotina e os seus passos, pelo id.",
    {"id": numero("Id da rotina")}, grupo="produtividade", risco=MODERADO, obrigatorios=["id"],
)
def rotina_apagar(ctx, id: int):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    ctx.banco.apagar_rotina(int(id))
    return {"mensagem": "Rotina apagada."}
