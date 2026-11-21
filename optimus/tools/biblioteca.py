"""Ferramentas da biblioteca de documentos: indexar uma pasta, listar e esquecer.

Deixa o Optimus "conversar com os seus documentos" offline: aponte uma pasta e ele indexa os
arquivos (txt, md, csv, html, PDF...) no conhecimento local, sem mandar nada para fora. Depois,
perguntas sobre o conteúdo são respondidas na hora, do próprio banco.
"""

from __future__ import annotations

from optimus import biblioteca
from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, resolver, texto


@ferramenta(
    "biblioteca_indexar",
    "Indexa todos os documentos de uma pasta (txt, md, csv, html, PDF...) no conhecimento local "
    "do Optimus, para responder sobre eles offline. Só reprocessa o que mudou. Nada sai do PC.",
    {"pasta": texto("Caminho da pasta com os documentos"),
     "recursivo": {"type": "boolean", "description": "Entrar nas subpastas (padrão: sim)"}},
    grupo="memoria", risco=MODERADO, obrigatorios=["pasta"],
)
def biblioteca_indexar(ctx, pasta: str, recursivo: bool = True):
    if not ctx or not getattr(ctx, "banco", None):
        return {"erro": "Sem banco de conhecimento para indexar."}
    alvo = resolver(ctx, pasta)
    if not alvo.is_dir():
        return {"erro": f"Pasta não encontrada: {alvo}"}
    resumo = biblioteca.indexar_pasta(ctx.banco, alvo, recursivo=recursivo)
    resumo["mensagem"] = (f"Indexei {resumo['indexados']} documento(s) de {alvo} "
                          f"({resumo['trechos']} trechos). "
                          f"{resumo['removidos']} removido(s), {resumo['ignorados']} ignorado(s).")
    return resumo


@ferramenta(
    "biblioteca_listar",
    "Lista os documentos já indexados na biblioteca local do Optimus (fonte e quantos trechos).",
    {}, grupo="memoria", risco=LIVRE,
)
def biblioteca_listar(ctx):
    if not ctx or not getattr(ctx, "banco", None):
        return {"documentos": []}
    docs = biblioteca.fontes(ctx.banco)
    return {"documentos": docs, "total": len(docs)}


@ferramenta(
    "biblioteca_esquecer",
    "Remove do conhecimento local todos os documentos de uma pasta que foram indexados antes.",
    {"pasta": texto("Caminho da pasta cujos documentos devem ser esquecidos")},
    grupo="memoria", risco=MODERADO, obrigatorios=["pasta"],
)
def biblioteca_esquecer(ctx, pasta: str):
    if not ctx or not getattr(ctx, "banco", None):
        return {"erro": "Sem banco de conhecimento."}
    alvo = resolver(ctx, pasta)
    removidos = biblioteca.esquecer_pasta(ctx.banco, alvo)
    return {"removidos": removidos, "mensagem": f"Esqueci {removidos} documento(s) de {alvo}."}
