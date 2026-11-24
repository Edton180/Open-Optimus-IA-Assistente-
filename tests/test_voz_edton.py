"""Voz "Edton Braz" (ElevenLabs Matheus) cadastrada, com reserva sem chave."""
from optimus.config import Config
from optimus.voice import tts


def test_voz_cadastrada_e_achada_pelo_nome():
    voz = tts.buscar_voz("Edton Braz")
    assert voz and voz.id == "edton-braz" and voz.base == tts.VOZ_EDTON_BRAZ
    assert tts.buscar_voz("edton").id == "edton-braz"


def test_sem_chave_cai_para_voz_brasileira():
    voz = tts.escolher_voz("edton-braz", online=True, chave_elevenlabs="")
    assert voz.id != "edton-braz" and voz.genero == "masculina"


def test_com_chave_usa_o_id_da_voz_e_elite_usa_a_configurada():
    cfg = Config({"voz": {"elevenlabs_chave": "x", "elevenlabs_voz": "OUTRA"}})
    assert tts.Falante("edton-braz", config=cfg)._id_elevenlabs() == tts.VOZ_EDTON_BRAZ
    assert tts.Falante("elite", config=cfg)._id_elevenlabs() == "OUTRA"


def test_aparece_no_estudio():
    from optimus.estudio import vozes

    assert any(p.nome == "Edton Braz" for p in vozes.listar())



def test_perfil_pessoal_edton_substitui_voz_publica_na_conversa(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from optimus.estudio import omnivoice, vozes

    amostra = tmp_path / "amostra.wav"
    amostra.write_bytes(b"amostra autorizada")
    perfil = SimpleNamespace(tipo="clonada", caminho_amostra=lambda: amostra)
    monkeypatch.setattr(vozes, "obter", lambda nome: perfil)
    chamadas = []
    monkeypatch.setattr(omnivoice, "gerar",
                        lambda texto, **kwargs: chamadas.append((texto, kwargs)) or [0.1, -0.1])
    monkeypatch.setattr(tts, "_wav_bytes", lambda onda, taxa: b"wav-pessoal")

    falante = tts.Falante("edton-braz", config=Config({"voz": {}}))
    audio, formato = falante.sintetizar("Olá, este é um teste.")

    assert formato == "wav"
    assert audio == b"wav-pessoal"
    assert chamadas and chamadas[0][1]["amostra"] == amostra
