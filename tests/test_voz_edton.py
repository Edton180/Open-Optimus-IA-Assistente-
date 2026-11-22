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
