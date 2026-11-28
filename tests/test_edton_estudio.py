"""Edton Braz no Estúdio: com a chave da ElevenLabs, usa a voz original pela API."""
import numpy as np

from optimus.config import Config
from optimus.estudio import motores, vozes
from optimus.voice import tts


def _capturar(monkeypatch):
    usados = []

    def falso(frase, perfil, velocidade, config):
        usados.append((perfil, config))
        return np.zeros(2400, dtype="float32") + 0.1

    monkeypatch.setattr(motores, "_gerar_padrao", falso)
    return usados


def test_com_chave_usa_a_voz_da_elevenlabs_sem_mexer_no_tom(monkeypatch):
    usados = _capturar(monkeypatch)
    cfg = Config({"voz": {"elevenlabs_chave": "chave"}})
    motores.gerar("Olá, tudo bem?", "Edton Braz", config=cfg)
    perfil, _ = usados[0]
    assert perfil.motor == "elevenlabs" and perfil.base == "edton-braz"
    assert perfil.tom == 0.0 and perfil.velocidade == 1.0
    falante = tts.Falante("edton-braz", config=cfg)
    assert falante.voz.motor == "elevenlabs"
    assert falante._id_elevenlabs() == tts.VOZ_EDTON_BRAZ


def test_em_ingles_tambem_vai_pela_elevenlabs(monkeypatch):
    usados = _capturar(monkeypatch)
    cfg = Config({"voz": {"elevenlabs_chave": "chave"}})
    motores.gerar("Hello there", "Edton Braz", idioma="en", config=cfg)
    assert usados and usados[0][0].motor == "elevenlabs"


def test_sem_chave_continua_a_aproximacao_local(monkeypatch):
    cfg = Config({"voz": {"elevenlabs_chave": ""}})
    perfil = vozes.obter("Edton Braz")
    assert motores._edton_pela_elevenlabs(perfil, cfg) is None


def test_outras_vozes_nao_mudam():
    cfg = Config({"voz": {"elevenlabs_chave": "chave"}})
    assert motores._edton_pela_elevenlabs(vozes.obter("Prime"), cfg) is None
