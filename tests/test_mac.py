"""Suporte ao macOS: testado com o sistema simulado (o CI roda em Linux e Windows)."""

import plistlib
import subprocess
from pathlib import Path

from optimus import startup
from optimus.config import Config
from optimus.tools import casa, controle
from optimus.tools import sistema as ferr_sistema
from optimus.tools.base import Contexto


def _ctx():
    return Contexto(config=Config())


def test_plataforma_reconhece_o_mac(monkeypatch):
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.setenv("PREFIX", "/usr")
    monkeypatch.setattr(startup.platform, "system", lambda: "Darwin")
    assert startup.plataforma() == "macos"


def test_launchd_plist_valido():
    comando = ["/usr/bin/python3", "-m", "optimus", "gui", "--sem-navegador"]
    dados = plistlib.loads(startup.texto_plist_mac(comando, Path("/tmp/a & b.log")).encode())
    assert dados["Label"] == startup.ROTULO_MAC
    assert dados["ProgramArguments"] == comando
    assert dados["RunAtLoad"] is True
    assert dados["StandardOutPath"] == "/tmp/a & b.log"  # caractere especial escapado


def test_script_de_volume_mac():
    assert controle.comando_volume_mac("definir", 140) == \
        "set volume output volume 100 without output muted"
    assert "+ 10" in controle.comando_volume_mac("aumentar", 10)
    assert "- 20" in controle.comando_volume_mac("baixar", 20)
    assert "muted" in controle.comando_volume_mac("mudo", 0)
    assert controle.comando_volume_mac("ver", 0) == "output volume of (get volume settings)"


class _Gravador:
    def __init__(self, saida=""):
        self.comandos, self.saida = [], saida

    def __call__(self, comando, *_a, **_k):
        self.comandos.append(comando)
        return subprocess.CompletedProcess(comando, 0, self.saida, "")


def test_volume_no_mac_usa_osascript(monkeypatch):
    gravador = _Gravador("35\n")
    monkeypatch.setattr(controle, "sistema", lambda: "macos")
    monkeypatch.setattr(controle, "_rodar", gravador)
    assert controle.volume(_ctx(), acao="ver") == {"volume": 35}
    controle.volume(_ctx(), acao="definir", valor=40)
    assert gravador.comandos[-1][:2] == ["osascript", "-e"]
    assert "volume 40" in gravador.comandos[-1][2]


def test_midia_no_mac_controla_o_player_aberto(monkeypatch):
    gravador = _Gravador("true")
    monkeypatch.setattr(controle, "sistema", lambda: "macos")
    monkeypatch.setattr(controle, "_rodar", gravador)
    resposta = controle.midia(_ctx(), acao="proxima")
    assert "Spotify" in resposta["mensagem"]
    assert gravador.comandos[-1][2] == 'tell application "Spotify" to next track'


def test_energia_e_apelidos_do_mac():
    assert "macos" in ferr_sistema._ENERGIA and "macos" in ferr_sistema._APELIDOS
    assert "pmset" in ferr_sistema._ENERGIA["macos"]["suspender"]
    # Um desligamento pelo System Events não tem como ser cancelado: não fingimos que tem.
    assert "cancelar" not in ferr_sistema._ENERGIA["macos"]


def test_vizinhos_arp_do_mac_e_ip_neigh_do_linux():
    mac = ("? (192.168.0.1) at 0:1a:2b:3:4:5 on en0 ifscope [ethernet]\n"
           "? (192.168.0.42) at a4:5e:60:d1:2:ff on en0 ifscope [ethernet]\n"
           "? (192.168.0.255) at ff:ff:ff:ff:ff:ff on en0 ifscope [ethernet]\n")
    assert casa.vizinhos_da_rede(mac) == [
        {"nome": "192.168.0.1", "mac": "00:1a:2b:03:04:05"},
        {"nome": "192.168.0.42", "mac": "a4:5e:60:d1:02:ff"},
    ]
    linux = "192.168.0.7 dev wlan0 lladdr 3c:22:fb:10:20:30 REACHABLE\n"
    assert casa.vizinhos_da_rede(linux) == [{"nome": "192.168.0.7", "mac": "3c:22:fb:10:20:30"}]
