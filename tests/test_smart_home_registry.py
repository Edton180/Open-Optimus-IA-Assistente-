import json

import pytest

from optimus.smart_home.registry import Dispositivo, RegistroDispositivos


def test_registro_persiste_e_recarrega_dispositivos(tmp_path):
    caminho = tmp_path / "data" / "devices.json"
    registro = RegistroDispositivos(caminho)
    registro.salvar(Dispositivo(
        id="onvif:192.168.1.20", nome="Câmera portão", integracao="onvif",
        fabricante="Genérica", host="192.168.1.20",
        capacidades=["snapshot", "video"], disponibilidade="online",
        confianca_estado="confirmed",
    ))

    recarregado = RegistroDispositivos(caminho)
    item = recarregado.obter("onvif:192.168.1.20")
    assert item["nome"] == "Câmera portão"
    assert item["capacidades"] == ["snapshot", "video"]
    assert item["confianca_estado"] == "confirmed"


def test_registro_nao_persiste_credenciais(tmp_path):
    caminho = tmp_path / "devices.json"
    registro = RegistroDispositivos(caminho)
    registro.salvar(Dispositivo(
        id="ha:light.sala", nome="Luz sala", integracao="home_assistant",
        entity_id="light.sala", disponibilidade="online",
        confianca_estado="confirmed",
    ))
    conteudo = caminho.read_text(encoding="utf-8").lower()
    assert "token" not in conteudo
    assert "password" not in conteudo
    assert "secret" not in conteudo


def test_registro_atualiza_remove_e_filtra(tmp_path):
    registro = RegistroDispositivos(tmp_path / "devices.json")
    registro.salvar(Dispositivo(id="ha:a", nome="A", integracao="home_assistant"))
    registro.salvar(Dispositivo(id="onvif:b", nome="B", integracao="onvif"))
    assert len(registro.listar("onvif")) == 1
    assert registro.remover("ha:a") is True
    assert registro.remover("ha:a") is False


def test_dispositivo_rejeita_identificador_e_estado_invalidos():
    with pytest.raises(ValueError):
        Dispositivo(id="../config", nome="Inválido", integracao="manual")
    with pytest.raises(ValueError):
        Dispositivo(id="x", nome="Inválido", integracao="manual",
                    confianca_estado="ligado-talvez")


def test_arquivo_corrompido_nao_impede_inicializacao(tmp_path):
    caminho = tmp_path / "devices.json"
    caminho.write_text("{invalido", encoding="utf-8")
    assert RegistroDispositivos(caminho).listar() == []
