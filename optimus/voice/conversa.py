"""Conversa por voz no terminal: palavra de ativação + modo conversa.

Diga "Optimus, ..." para chamar. Depois de cada resposta, por alguns segundos, dá para
continuar falando sem repetir a palavra (modo conversa). Diga "pode parar" ou "tchau" para
encerrar o modo conversa. Ctrl+C sai.
"""

from __future__ import annotations

import re
import time

from optimus.safety import interpretar_confirmacao
from optimus.voice.stt import (Ouvinte, contem_palavra_ativacao, gravar_ate_silencio,
                               ouvir_android)
from optimus.voice.tts import Falante

JANELA_CONVERSA = 25.0


def conversar_por_voz(agente, config, ao_texto=print) -> None:
    from optimus.tools.base import no_android

    voz_cfg = config["voz"]
    falante = Falante(voz_cfg.get("voz") or "feminina", voz_cfg.get("velocidade", 1.0))
    ouvinte = None if no_android() else Ouvinte(
        voz_cfg.get("modelo_stt") or (agente.perfil.modelo_stt if agente.perfil else "small"))
    palavra = voz_cfg.get("palavra_ativacao") or "optimus"
    historico: list[dict] = []
    ultima_resposta = 0.0

    def ouvir() -> str:
        if ouvinte is None:
            return ouvir_android()
        audio = gravar_ate_silencio()
        return ouvinte.transcrever(audio) if audio is not None else ""

    def confirmar_por_voz(chamada, avaliacao) -> bool:
        exigencia = ' Diga "confirmo" para continuar.' if avaliacao.nivel >= 2 else \
            " Posso continuar?"
        pergunta = f"Atenção: vou {avaliacao.motivo}.{exigencia}"
        ao_texto(f"[confirmação] {pergunta}")
        falante.falar(pergunta)
        resposta = ouvir()
        ao_texto(f"[você] {resposta}")
        return interpretar_confirmacao(resposta, avaliacao.nivel)

    agente.confirmar = confirmar_por_voz
    ao_texto(f'Ouvindo. Diga "{palavra.capitalize()}" para chamar (Ctrl+C para sair). '
             f"Voz: {falante.voz.nome} ({falante.voz.descricao}).")
    falante.falar("Optimus online. Estou ouvindo.")
    while True:
        texto = ouvir()
        if not texto:
            continue
        em_conversa = time.monotonic() - ultima_resposta < JANELA_CONVERSA
        achou, resto = contem_palavra_ativacao(texto, palavra)
        if not achou and not em_conversa:
            continue
        pedido = resto if achou else texto
        if re.search(r"\b(pode parar|tchau|encerrar conversa|so isso|só isso)\b", pedido.lower()):
            ultima_resposta = 0.0
            falante.falar("Certo. Estou aqui se precisar.")
            continue
        if not pedido:
            falante.falar("Sim?")
            ultima_resposta = time.monotonic()
            continue
        ao_texto(f"[você] {pedido}")
        resposta = agente.responder(pedido, historico, por_voz=True)
        historico += [{"role": "user", "content": pedido},
                      {"role": "assistant", "content": resposta}]
        historico = historico[-20:]
        ao_texto(f"[optimus] {resposta}")
        if voz_cfg.get("falar_respostas", True):
            falante.falar(resposta)
        ultima_resposta = time.monotonic()
