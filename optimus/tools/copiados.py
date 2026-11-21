"""Histórico de copiados (aba Copiados do painel).

Guarda o que você copia (Ctrl+C) no banco local, no seu PC, para você achar e reusar
depois. A captura é opcional e fica desligada por padrão (ligue em [copiados] ativo = true),
porque ler a área de transferência é sensível. Nada sai do PC.
"""

from __future__ import annotations

from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, numero


def _sem_banco(ctx) -> bool:
    return not ctx or not getattr(ctx, "banco", None)


@ferramenta(
    "copiados_listar",
    "Lista os últimos textos copiados (área de transferência), do mais recente ao mais antigo.",
    {"limite": numero("Quantos mostrar (padrão 20)")},
    grupo="produtividade", risco=LIVRE, obrigatorios=[],
)
def copiados_listar(ctx, limite: float = 20):
    if _sem_banco(ctx):
        return {"copiados": []}
    itens = ctx.banco.listar_copiados(int(limite) if limite else 20)
    return {"copiados": [{"id": i["id"], "texto": i["texto"], "quando": i["quando"]}
                         for i in itens]}


@ferramenta(
    "copiado_usar",
    "Copia de volta para a área de transferência um item do histórico, pelo id.",
    {"id": numero("Id do item do histórico")},
    grupo="produtividade", risco=MODERADO, obrigatorios=["id"],
)
def copiado_usar(ctx, id: int):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    item = ctx.banco.copiado(int(id))
    if not item:
        return {"erro": "Não achei esse item no histórico."}
    try:
        import pyperclip
    except ImportError:
        return {"erro": "Instale o extra de desktop: pip install optimus-assistente[desktop]"}
    pyperclip.copy(item["texto"])
    return {"mensagem": "Coloquei de volta na área de transferência.", "texto": item["texto"]}


@ferramenta(
    "copiado_apagar",
    "Apaga um item do histórico de copiados, pelo id.",
    {"id": numero("Id do item")}, grupo="produtividade", risco=MODERADO, obrigatorios=["id"],
)
def copiado_apagar(ctx, id: int):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    ctx.banco.apagar_copiado(int(id))
    return {"mensagem": "Item apagado do histórico."}


@ferramenta(
    "copiados_limpar",
    "Apaga todo o histórico de copiados.",
    {}, grupo="produtividade", risco=MODERADO,
)
def copiados_limpar(ctx):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    ctx.banco.limpar_copiados()
    return {"mensagem": "Histórico de copiados limpo."}
