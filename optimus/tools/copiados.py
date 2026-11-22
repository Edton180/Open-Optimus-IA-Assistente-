"""Histórico de copiados (aba Copiados do painel).

Guarda o que você copia (Ctrl+C) no banco local, no seu PC, para você achar e reusar
depois. A captura é opcional e fica desligada por padrão (ligue em [copiados] ativo = true),
porque ler a área de transferência é sensível.

Privacidade: o conteúdo copiado pode ser sensível (senhas, tokens, mensagens). Para não
mandar isso para fora do PC sem querer — o resultado de uma ferramenta volta para o modelo,
que pode ser um serviço na nuvem —, estas ferramentas devolvem só uma prévia curta, nunca o
texto inteiro. `copiado_usar` coloca o texto de volta na área de transferência direto no PC,
sem passar pelo modelo.
"""

from __future__ import annotations

from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, numero


def _sem_banco(ctx) -> bool:
    return not ctx or not getattr(ctx, "banco", None)


def _previa(texto: str, limite: int = 80) -> str:
    """Prévia de uma linha, curta, para o usuário reconhecer o item sem expor tudo."""
    uma_linha = " ".join((texto or "").split())
    return uma_linha if len(uma_linha) <= limite else uma_linha[:limite - 1] + "…"


@ferramenta(
    "copiados_listar",
    "Lista os últimos textos copiados (área de transferência), do mais recente ao mais antigo. "
    "Mostra só uma prévia curta de cada um; use copiado_usar para colocar o item inteiro de "
    "volta na área de transferência.",
    {"limite": numero("Quantos mostrar (padrão 20)")},
    grupo="produtividade", risco=LIVRE, obrigatorios=[],
)
def copiados_listar(ctx, limite: float = 20):
    if _sem_banco(ctx):
        return {"copiados": []}
    itens = ctx.banco.listar_copiados(int(limite) if limite else 20)
    return {"copiados": [{"id": i["id"], "previa": _previa(i["texto"]),
                          "tamanho": len(i["texto"]), "quando": i["quando"]} for i in itens],
            "nota": "Prévias apenas; o texto inteiro fica no PC. Use copiado_usar pelo id."}


@ferramenta(
    "copiado_usar",
    "Copia de volta para a área de transferência um item do histórico, pelo id. O texto é "
    "colocado direto na área de transferência do PC (não é mostrado aqui).",
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
    return {"mensagem": "Coloquei de volta na área de transferência.",
            "previa": _previa(item["texto"]), "tamanho": len(item["texto"])}


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
