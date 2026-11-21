"""Controle de aparelhos na rede sem Home Assistant (TP-Link Kasa).

A parte de rede precisa de aparelho real; aqui testamos o que dá para testar sem rede:
a cifra do protocolo, os comandos montados e a leitura do estado.
"""

import json

from optimus.config import Config
from optimus.tools import ferramentas_ativas, lan
from optimus.roteador import selecionar_ferramentas


def test_cifra_kasa_ida_e_volta():
    for texto in ('{"system":{"get_sysinfo":{}}}', "ligar a tomada da sala", ""):
        cifrado = lan.cifrar_kasa(texto)
        assert cifrado == lan.cifrar_kasa(texto)  # determinístico
        assert lan.decifrar_kasa(cifrado) == texto
    # O primeiro byte segue o protocolo (chave inicial 171 XOR primeiro caractere).
    assert lan.cifrar_kasa("{")[0] == 171 ^ ord("{")


def test_payload_kasa():
    assert lan.payload_kasa("estado") == {"system": {"get_sysinfo": {}}}
    assert lan.payload_kasa("ligar") == {"system": {"set_relay_state": {"state": 1}}}
    assert lan.payload_kasa("desligar") == {"system": {"set_relay_state": {"state": 0}}}
    brilho = lan.payload_kasa("brilho", "80")
    luz = brilho["smartlife.iot.smartbulb.lightingservice"]["transition_light_state"]
    assert luz == {"on_off": 1, "brightness": 80}
    # brilho fora da faixa é limitado a 1-100
    assert lan.payload_kasa("brilho", "0")[
        "smartlife.iot.smartbulb.lightingservice"]["transition_light_state"]["brightness"] == 1


def test_estado_e_erro():
    sysinfo = {"system": {"get_sysinfo": {"alias": "Tomada da Sala", "relay_state": 1,
                                          "model": "HS100"}}}
    info = lan._nome_e_estado(sysinfo)
    assert info == {"nome": "Tomada da Sala", "ligado": True, "modelo": "HS100"}
    ok = {"system": {"set_relay_state": {"err_code": 0}}}
    ruim = {"system": {"set_relay_state": {"err_code": -3, "err_msg": "invalid argument"}}}
    assert lan._erro_kasa(ok) == ""
    assert lan._erro_kasa(ruim) == "invalid argument"


def test_kasa_vai_para_o_modelo_sem_home_assistant():
    # Sem Home Assistant configurado, o controle da casa é pelas ferramentas Kasa.
    todas = ferramentas_ativas(Config())
    escolhidas = selecionar_ferramentas("ligue a tomada da sala", todas, pequeno=True)
    assert "kasa_controlar" in escolhidas
    assert "casa_controlar" not in escolhidas  # filtrada por falta de Home Assistant
