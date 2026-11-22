"""Apagar itens e limpar o histórico do Estúdio de voz."""
from optimus import estudio


def test_apagar_item_e_limpar_mantendo_favoritos(tmp_path):
    saida = estudio.pasta_saidas() / "fala.mp3"
    saida.write_bytes(b"x")
    fora = tmp_path / "meu.mp3"
    fora.write_bytes(b"x")
    a = estudio.registrar("falar", saida, "olá", "Prime")
    b = estudio.registrar("falar", fora, "tchau", "Prime")
    c = estudio.registrar("falar", "x.mp3", "fica", "Prime")
    estudio.favoritar(c["id"])
    assert estudio.apagar_historico(a["id"], apagar_arquivos=True) == 1
    assert not saida.exists()  # arquivo da pasta de saídas apagado
    assert estudio.apagar_historico(tudo=True, apagar_arquivos=True) == 1  # b sai, c fica
    assert fora.exists()  # arquivo fora das pastas do Estúdio nunca é apagado
    assert [i["id"] for i in estudio.historico()] == [c["id"]]
    assert estudio.apagar_historico(tudo=True, manter_favoritos=False) == 1
    assert estudio.historico() == []
    assert estudio.apagar_historico("nao-existe") == 0


def test_rota_delete_do_historico():
    from optimus.web import estudio_api

    item = estudio.registrar("falar", "x.mp3", "olá", "Prime")

    from optimus.config import Config

    class Falso:
        config = Config()
        motor = None

    status, dados = estudio_api.atender("DELETE", ["historico", item["id"]], {}, "", b"",
                                        Falso())
    assert status == 200 and dados["removidos"] == 1
    estudio.registrar("falar", "y.mp3", "oi", "Prime")
    status, dados = estudio_api.atender("DELETE", ["historico"], {}, "", b"", Falso())
    assert dados["removidos"] == 1 and estudio.historico() == []
