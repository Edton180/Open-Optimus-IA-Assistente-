"""Ferramentas do próprio assistente: voz, lembretes, conversas antigas e imagens."""

from __future__ import annotations

import re
import time
import urllib.parse

import httpx

from optimus.config import pasta_base
from optimus.tools.base import ferramenta, texto


@ferramenta(
    "trocar_voz",
    "Troca a voz do Optimus: Prime, Valkyrie, Nexus, Cyber, Stealth, Elite, Aurora, Lyra, "
    "Titan ou Sistema.",
    {"voz": texto("Nome da voz")}, grupo="geral",
)
def trocar_voz(ctx, voz: str):
    from optimus.voice import tts

    escolhida = tts.buscar_voz(voz)
    if not escolhida:
        nomes = ", ".join(v.nome for v in tts.VOZES)
        return {"erro": f"Não conheço a voz '{voz}'. Vozes: {nomes}."}
    ctx.config.definir("voz", "voz", escolhida.id)
    ctx.config.salvar()
    chave = ctx.config.get("voz", "elevenlabs_chave", "")
    real = tts.escolher_voz(escolhida.id, chave_elevenlabs=chave)
    aviso = "" if real.id == escolhida.id else \
        f" Ela não está disponível neste PC agora, então vou usar a {real.nome}."
    return {"mensagem": f"Pronto, agora falo com a voz {escolhida.nome}.{aviso}",
            "voz": escolhida.id}


@ferramenta("listar_vozes", "Lista as vozes do Optimus e quais funcionam neste PC.",
            grupo="geral")
def listar_vozes(ctx):
    from optimus.voice import tts

    chave = ctx.config.get("voz", "elevenlabs_chave", "")
    return {"itens": [{"nome": v.nome, "descricao": v.descricao,
                       "disponivel": tts.voz_disponivel(v, True, chave)} for v in tts.VOZES]}


@ferramenta(
    "cancelar_lembretes",
    "Cancela lembretes pendentes: todos, ou só os que contêm um texto.",
    {"texto": texto("Opcional: só os lembretes que contêm este texto")},
    grupo="lembretes", obrigatorios=[],
)
def cancelar_lembretes(ctx, texto: str = ""):
    total = ctx.banco.cancelar_lembretes(texto or "")
    return {"mensagem": f"{total} lembrete(s) cancelado(s)." if total else
            "Não havia lembretes pendentes."}


@ferramenta(
    "buscar_conversas",
    "Procura em conversas antigas com o usuário (o que ele disse ou pediu antes).",
    {"assunto": texto("Assunto")}, grupo="memoria",
)
def buscar_conversas(ctx, assunto: str):
    achados = ctx.banco.buscar_mensagens(assunto)
    return {"total": len(achados), "itens": [
        {"nome": a["titulo"], "quem": "usuário" if a["papel"] == "user" else "Optimus",
         "quando": time.strftime("%d/%m %H:%M", time.localtime(a["quando"])),
         "trecho": a["trecho"]} for a in achados]}


def pasta_imagens():
    pasta = pasta_base() / "imagens"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


@ferramenta(
    "gerar_imagem",
    "Cria uma imagem a partir de uma descrição. Usa o Stable Diffusion do PC (AUTOMATIC1111 ou "
    "Forge, se estiver aberto) e, sem ele, um gerador gratuito na internet (Pollinations). "
    "Escreva a descrição em inglês para melhor resultado.",
    {"descricao": texto("O que desenhar, com estilo, cores e enquadramento"),
     "formato": {"type": "string", "enum": ["quadrado", "paisagem", "retrato"],
                 "description": "Formato da imagem"}},
    grupo="internet", obrigatorios=["descricao"],
)
def gerar_imagem(ctx, descricao: str, formato: str = "quadrado"):
    largura, altura = {"paisagem": (1216, 832), "retrato": (832, 1216)}.get(formato, (1024, 1024))
    nome = re.sub(r"[^a-z0-9]+", "-", descricao.lower())[:40].strip("-") or "imagem"
    destino = pasta_imagens() / f"{time.strftime('%Y%m%d-%H%M%S')}-{nome}.png"
    url_local = (ctx.config.get("imagem", "url", "") or "http://127.0.0.1:7860").rstrip("/")
    try:
        resposta = httpx.post(f"{url_local}/sdapi/v1/txt2img", timeout=300, json={
            "prompt": descricao, "width": min(largura, 1024), "height": min(altura, 1024),
            "steps": 25})
        if resposta.status_code == 200:
            import base64

            destino.write_bytes(base64.b64decode(resposta.json()["images"][0]))
            return {"mensagem": "Imagem criada no PC (Stable Diffusion local).",
                    "imagem": f"/api/midia/imagens/{destino.name}", "arquivo": str(destino)}
    except httpx.HTTPError:
        pass  # sem Stable Diffusion local: usa o gerador online
    if not ctx.config.get("imagem", "online", True):
        return {"erro": "Não há Stable Diffusion aberto neste PC e o gerador online está "
                        "desligado em [imagem] online."}
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(descricao) +
           f"?width={largura}&height={altura}&nologo=true&seed={int(time.time()) % 100000}")
    try:
        resposta = httpx.get(url, timeout=180, follow_redirects=True)
    except httpx.HTTPError as erro:
        return {"erro": f"Sem acesso ao gerador online ({type(erro).__name__}). Confira a "
                        "internet ou abra o Stable Diffusion no PC."}
    if resposta.status_code != 200 or not resposta.headers.get("content-type", "").startswith(
            "image"):
        return {"erro": f"O gerador online respondeu {resposta.status_code}. Tente de novo."}
    destino = destino.with_suffix(".jpg")
    destino.write_bytes(resposta.content)
    return {"mensagem": "Imagem criada (gerador online Pollinations).",
            "imagem": f"/api/midia/imagens/{destino.name}", "arquivo": str(destino)}
