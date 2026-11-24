from types import SimpleNamespace
import ipaddress
import socket

import pytest

from optimus.tools import rede_wifi


def _interface(ip="192.168.1.10", mask="255.255.255.0"):
    return SimpleNamespace(family=socket.AF_INET, address=ip, netmask=mask)


def test_redes_locais_lista_somente_interfaces_privadas_ativas(monkeypatch):
    monkeypatch.setattr(rede_wifi.psutil, "net_if_addrs", lambda: {
        "wifi": [_interface()],
        "loopback": [_interface("127.0.0.1")],
        "publica": [_interface("8.8.8.8")],
    })
    monkeypatch.setattr(rede_wifi.psutil, "net_if_stats", lambda: {
        "wifi": SimpleNamespace(isup=True),
        "loopback": SimpleNamespace(isup=True),
        "publica": SimpleNamespace(isup=True),
    })

    redes = rede_wifi.redes_locais()

    assert redes == [{"interface": "wifi", "ip_local": "192.168.1.10",
                      "rede": "192.168.1.0/24", "varredura_disponivel": True}]


def test_validar_rede_restringe_a_subrede_privada_local():
    locais = [{"interface": "wifi", "ip_local": "192.168.1.10",
               "rede": "192.168.1.0/24"}]
    assert str(rede_wifi.validar_rede("192.168.1.0/25", locais)) == "192.168.1.0/25"
    with pytest.raises(ValueError, match="privadas"):
        rede_wifi.validar_rede("8.8.8.0/24", locais)
    with pytest.raises(ValueError, match="não pertence"):
        rede_wifi.validar_rede("192.168.2.0/24", locais)
    with pytest.raises(ValueError, match="256"):
        rede_wifi.validar_rede("192.168.0.0/16", locais)


def test_descobrir_cruza_ping_com_cache_arp(monkeypatch):
    monkeypatch.setattr(rede_wifi, "_ping", lambda ip: ip.endswith(".2"))
    monkeypatch.setattr(rede_wifi, "_ler_vizinhos", lambda: {
        "192.168.1.3": "aa:bb:cc:dd:ee:ff"
    })
    resultado = rede_wifi.descobrir(ipaddress.ip_network("192.168.1.0/29"), "192.168.1.1")

    assert resultado["total"] == 2
    assert resultado["dispositivos"][0]["ip"] == "192.168.1.2"
    assert resultado["dispositivos"][0]["estado"] == "respondendo ao ping"
    assert resultado["dispositivos"][1]["mac"] == "aa:bb:cc:dd:ee:ff"


def test_tool_rede_wifi_varrer_nao_varre_sem_interface_local(monkeypatch):
    monkeypatch.setattr(rede_wifi, "redes_locais", lambda: [])
    resultado = rede_wifi.rede_wifi_varrer(None)
    assert "erro" in resultado
    assert resultado["interfaces"] == []

def test_rede_maior_permite_escolher_subrede_local_limitada():
    locais = [{"interface": "wifi", "ip_local": "10.0.1.10",
               "rede": "10.0.0.0/16", "varredura_disponivel": False}]
    assert str(rede_wifi.validar_rede("10.0.1.0/24", locais)) == "10.0.1.0/24"
