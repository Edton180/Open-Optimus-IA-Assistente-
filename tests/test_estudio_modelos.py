"""Batch installation safeguards for voice and audio models."""

from collections import namedtuple

import pytest

from optimus.estudio import modelos


def _item(ident, tamanho=100):
    return modelos.Item(ident, ident, "voz", "MIT", tamanho, "teste", "arquivo",
                        pastas=[])


def test_instalar_todos_continua_apos_falha(monkeypatch, tmp_path):
    itens = [_item("a"), _item("b"), _item("c")]
    monkeypatch.setattr(modelos, "catalogo", lambda: itens)
    Uso = namedtuple("Uso", "total used free")
    monkeypatch.setattr(modelos.shutil, "disk_usage", lambda _: Uso(10_000, 0, 10_000 * 1024 * 1024))
    chamados = []

    def instalar(ident, progresso=None):
        chamados.append(ident)
        if ident == "b":
            raise RuntimeError("download interrompido")
        return {"id": ident}

    monkeypatch.setattr(modelos, "instalar", instalar)
    resultado = modelos.instalar_todos()
    assert chamados == ["a", "b", "c"]
    assert resultado["total"] == 3
    assert resultado["instalados"] == 2
    assert resultado["falhas"][0]["id"] == "b"


def test_instalar_todos_bloqueia_sem_espaco(monkeypatch):
    monkeypatch.setattr(modelos, "catalogo", lambda: [_item("modelo", 500)])
    Uso = namedtuple("Uso", "total used free")
    monkeypatch.setattr(modelos.shutil, "disk_usage", lambda _: Uso(100, 95, 5 * 1024 * 1024))
    with pytest.raises(modelos.ErroEstudio, match="Espaço insuficiente"):
        modelos.instalar_todos()


def test_modelo_de_pacote_com_pesos_nao_fica_pronto_so_com_pip(monkeypatch, tmp_path):
    item = modelos.Item("omnivoice", "OmniVoice", "clonagem", "Apache-2.0", 2500,
                        "teste", "pacote", "omnivoice", "omnivoice")
    monkeypatch.setattr(modelos, "_marcador", lambda _: tmp_path / "omnivoice.ok")
    monkeypatch.setattr(modelos.importlib.util, "find_spec", lambda _: object())
    assert not item.instalado()
    (tmp_path / "omnivoice.ok").write_text("ok", encoding="utf-8")
    assert item.instalado()
