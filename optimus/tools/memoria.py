"""Memória de longo prazo e lembretes."""

from __future__ import annotations

import datetime as dt
import time

from optimus.tools.base import ferramenta, numero, texto


@ferramenta("lembrar", "Guarda um fato importante sobre o usuário para sempre (nome, "
            "preferências, projetos, contatos). Use quando o usuário pedir para lembrar algo ou "
            "contar algo pessoal útil.", {"fato": texto("O fato, numa frase")}, grupo="memoria")
def lembrar(ctx, fato: str):
    ctx.banco.lembrar_fato(fato)
    return {"mensagem": f"Guardei: {fato}"}


@ferramenta("recordar", "Procura na memória de longo prazo o que você sabe sobre um assunto.",
            {"assunto": texto("Assunto")}, grupo="memoria")
def recordar(ctx, assunto: str):
    return {"assunto": assunto, "itens": ctx.banco.buscar_fatos(assunto)}


@ferramenta("criar_lembrete", "Cria um lembrete ou alarme. Informe em quantos minutos, ou um "
            "horário HH:MM. 'repetir_minutos' repete (ex.: 60 = de hora em hora).",
            {"texto": texto("Do que lembrar"), "minutos": numero("Daqui a quantos minutos"),
             "horario": texto("Ou um horário, ex.: 14:30"),
             "repetir_minutos": numero("Repetir a cada N minutos (0 = não)")},
            grupo="lembretes", obrigatorios=["texto"])
def criar_lembrete(ctx, texto: str, minutos: int = 0, horario: str = "",
                   repetir_minutos: int = 0):
    if horario:
        hora, minuto = (int(x) for x in horario.replace("h", ":").split(":")[:2])
        alvo = dt.datetime.now().replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if alvo < dt.datetime.now():
            alvo += dt.timedelta(days=1)
        quando = alvo.timestamp()
    else:
        quando = time.time() + max(1, int(minutos or 10)) * 60
    ctx.banco.criar_lembrete(texto, quando, int(repetir_minutos or 0))
    return {"mensagem": "Lembrete criado para " +
            dt.datetime.fromtimestamp(quando).strftime("%d/%m às %H:%M") + f": {texto}"}


@ferramenta("listar_lembretes", "Mostra os lembretes pendentes.", grupo="lembretes")
def listar_lembretes(ctx):
    return {"itens": [{"nome": l["texto"], "quando": dt.datetime.fromtimestamp(l["quando"])
                       .strftime("%d/%m %H:%M")} for l in ctx.banco.lembretes()]}


@ferramenta("aprender", "Estuda um site, arquivo ou texto e guarda na base de conhecimento "
            "local para consultar depois (mesmo offline). Use quando o usuário pedir para "
            "aprender, estudar ou guardar um conteúdo.",
            {"fonte": texto("Link (https://...), caminho de arquivo ou um texto"),
             "titulo": texto("Nome curto para o conteúdo (opcional)")},
            grupo="memoria", obrigatorios=["fonte"])
def aprender(ctx, fonte: str, titulo: str = ""):
    from optimus.tools.base import resolver

    fonte = fonte.strip()
    if fonte.startswith(("http://", "https://", "www.")):
        from optimus.tools.internet import ler_pagina

        pagina = ler_pagina(ctx, fonte)
        conteudo, titulo = pagina["texto"], titulo or pagina["titulo"] or fonte
        chave = pagina["url"]
    else:
        caminho = resolver(ctx, fonte) if len(fonte) < 400 else None
        if caminho and caminho.is_file():
            if caminho.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                except ImportError:
                    return {"erro": "Para ler PDF instale: pip install pypdf"}
                conteudo = "\n".join(p.extract_text() or "" for p in PdfReader(str(caminho)).pages)
            else:
                conteudo = caminho.read_text(encoding="utf-8", errors="replace")
            titulo, chave = titulo or caminho.name, str(caminho)
        else:
            conteudo, titulo = fonte, titulo or fonte[:40]
            chave = "texto:" + titulo
    trechos = ctx.banco.aprender(chave, titulo, conteudo)
    return {"mensagem": f"Aprendi '{titulo}' ({trechos} trechos guardados)."}


@ferramenta("consultar_conhecimento", "Procura na base de conhecimento local (o que você já "
            "aprendeu com sites, arquivos e textos).", {"pergunta": texto("O que procurar")},
            grupo="memoria")
def consultar_conhecimento(ctx, pergunta: str):
    achados = ctx.banco.consultar(pergunta)
    if not achados:
        return {"mensagem": "Não encontrei nada sobre isso na base de conhecimento."}
    return {"itens": [{"nome": a["titulo"], "fonte": a["fonte"], "trecho": a["trecho"][:1500]}
                      for a in achados]}
