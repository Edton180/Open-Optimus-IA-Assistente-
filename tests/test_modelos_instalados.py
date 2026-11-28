"""Correções do relato do celular: modelo rápido não instalado, download que "baixou" sem
baixar, botão preso em "Baixando…" e motores instalados que o Optimus não enxergava."""

import json
import threading
import time
import urllib.request
from collections import namedtuple
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from optimus import pacotes
from optimus.agent import Agente
from optimus.app import Optimus
from optimus.config import Config
from optimus.engine.base import Motor
from optimus.engine.ollama import MotorOllama
from optimus.web import server

Memoria = namedtuple("Memoria", "available")


class MotorLista(Motor):
    def __init__(self, nomes):
        self.nomes = nomes

    def modelos(self):
        return list(self.nomes)

    def disponivel(self):
        return True


class Perfil:
    modelo = "qwen3.5:4b"
    modelo_rapido = "qwen3.5:0.8b"


def _agente(nomes, modelo="qwen3.5:2b", rapido=""):
    config = Config()
    config.definir("motor", "modelo", modelo)
    config.definir("motor", "modelo_rapido", rapido)
    avisos = []
    a = Agente(config=config, motor=MotorLista(nomes), perfil=Perfil(),
               ao_evento=lambda e: avisos.append(e.get("texto", "")))
    return a, avisos


def test_pouca_ram_nao_escolhe_modelo_rapido_que_nao_esta_instalado(monkeypatch):
    monkeypatch.setattr("optimus.agent.psutil.virtual_memory", lambda: Memoria(0.5 * 1024**3))
    a, avisos = _agente(["qwen3.5:2b", "gemma3:1b"])
    # o perfil sugere qwen3.5:0.8b, que não está no Ollama: usa o menor que está
    assert a.escolher_modelo("oi", por_voz=False) == "gemma3:1b"
    assert any("gemma3:1b" in t for t in avisos)


def test_pouca_ram_sem_modelo_menor_fica_no_principal_sem_falso_aviso(monkeypatch):
    monkeypatch.setattr("optimus.agent.psutil.virtual_memory", lambda: Memoria(0.5 * 1024**3))
    a, avisos = _agente(["qwen3.5:2b"])
    assert a.escolher_modelo("oi", por_voz=False) == "qwen3.5:2b"
    assert not any("modelo rápido" in t for t in avisos)


def test_modelo_rapido_instalado_e_usado(monkeypatch):
    monkeypatch.setattr("optimus.agent.psutil.virtual_memory", lambda: Memoria(0.5 * 1024**3))
    a, _ = _agente(["qwen3.5:2b", "qwen3.5:0.8b", "gemma3:1b"])
    assert a.escolher_modelo("oi", por_voz=False) == "qwen3.5:0.8b"


def test_principal_nao_instalado_usa_um_que_esta(monkeypatch):
    monkeypatch.setattr("optimus.agent.psutil.virtual_memory", lambda: Memoria(8 * 1024**3))
    a, avisos = _agente(["qwen3.5:2b", "nomic-embed-text:latest"], modelo="qwen3.5:9b")
    assert a.escolher_modelo("escreva um texto longo", por_voz=False) == "qwen3.5:2b"
    assert any("não está instalado" in t for t in avisos)


def test_motor_sem_lista_confia_na_configuracao(monkeypatch):
    monkeypatch.setattr("optimus.agent.psutil.virtual_memory", lambda: Memoria(0.5 * 1024**3))
    a, _ = _agente([], modelo="gpt-x", rapido="gpt-x-mini")
    assert a.escolher_modelo("oi", por_voz=False) == "gpt-x-mini"


# ------------------------------------------------------------------ download pelo Ollama
class OllamaPull(BaseHTTPRequestHandler):
    linhas: list[dict] = []
    tags: list[str] = []
    status = 200

    def log_message(self, *a):
        pass

    def do_GET(self):
        corpo = json.dumps({"models": [{"name": n} for n in OllamaPull.tags]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if OllamaPull.status != 200:
            corpo = json.dumps({"error": "pull model manifest: file does not exist"}).encode()
            self.send_response(OllamaPull.status)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
            return
        self.send_response(200)
        self.end_headers()
        for linha in OllamaPull.linhas:
            self.wfile.write((json.dumps(linha) + "\n").encode())


def _ollama(linhas, tags, status=200):
    OllamaPull.linhas, OllamaPull.tags, OllamaPull.status = linhas, tags, status
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OllamaPull)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, MotorOllama(f"http://127.0.0.1:{httpd.server_address[1]}")


def test_download_que_para_no_meio_nao_conta_como_baixado():
    httpd, motor = _ollama([{"status": "pulling", "total": 100, "completed": 30}], [])
    erros = []
    try:
        assert motor.baixar("qwen3.5:0.8b", lambda d: erros.append(d.get("error"))) is False
    finally:
        httpd.shutdown()
    assert "parou antes de terminar" in (erros[-1] or "")


def test_erro_do_ollama_chega_na_tela():
    httpd, motor = _ollama([], [], status=500)
    erros = []
    try:
        assert motor.baixar("nao-existe", lambda d: erros.append(d.get("error"))) is False
    finally:
        httpd.shutdown()
    assert "does not exist" in erros[-1]


def test_sucesso_confere_a_lista_do_ollama():
    httpd, motor = _ollama([{"status": "success"}], ["qwen3.5:0.8b"])
    try:
        assert motor.baixar("qwen3.5:0.8b") is True
        OllamaPull.tags = ["outro:1b"]
        assert motor.baixar("qwen3.5:0.8b") is False
    finally:
        httpd.shutdown()


def _req(url, dados=None):
    corpo = json.dumps(dados).encode() if dados is not None else None
    pedido = urllib.request.Request(url, data=corpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=10) as r:
        return json.loads(r.read())


class MotorQuebra(MotorLista):
    def baixar(self, modelo, progresso=None):
        raise RuntimeError("disco cheio")


def test_download_com_erro_termina_e_mostra_o_motivo():
    config = Config()
    config.definir("motor", "backend", "demo")
    optimus = Optimus(config)
    optimus.motor = MotorQuebra(["qwen3.5:2b"])
    server.Manipulador.estado = server.Estado(optimus)
    server.Manipulador.senha = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Manipulador)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _req(url + "/api/modelos/baixar", {"modelo": "gemma3:1b"})
        for _ in range(50):
            p = _req(url + "/api/modelos/progresso").get("gemma3:1b", {})
            if p.get("terminou"):
                break
            time.sleep(0.05)
        assert p["terminou"] and p["ok"] is False and "disco cheio" in p["erro"]
        catalogo = _req(url + "/api/modelos/catalogo")
        assert catalogo["instalados"] == ["qwen3.5:2b"]
    finally:
        httpd.shutdown()


# ------------------------------------------------------------------ motores instalados
def test_pacote_instalado_depois_de_abrir_e_reconhecido(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    assert not pacotes.modulo_instalado("motor_novo_optimus")
    (tmp_path / "motor_novo_optimus").mkdir()
    (tmp_path / "motor_novo_optimus" / "__init__.py").write_text("")
    assert pacotes.modulo_instalado("motor_novo_optimus")


def test_comando_pip_usa_o_python_do_optimus(monkeypatch):
    monkeypatch.setattr(pacotes.sys, "executable", "C:/Program Files/Optimus/python.exe")
    assert pacotes.comando_pip("sherpa-onnx<2") == \
        '"C:/Program Files/Optimus/python.exe" -m pip install "sherpa-onnx<2"'


# ------------------------------------------------------------------ microfone no celular
def test_https_para_o_microfone_do_celular(tmp_path, monkeypatch):
    import ssl

    import pytest

    from optimus.web import certificado

    import ipaddress

    rede = ipaddress.ip_network("10.0.0.0/24")  # IPs de exemplo da rede de casa
    ip_a, ip_b = str(rede[20]), str(rede[30])
    monkeypatch.setattr(certificado, "pasta_base", lambda: tmp_path)
    if certificado.garantir([ip_a]) is None:
        pytest.skip("sem cryptography e sem openssl neste ambiente")
    cert, chave = certificado.arquivos()
    assert cert.exists() and chave.exists()
    # mesmo IP: reaproveita; IP novo: recria
    antes = cert.read_bytes()
    certificado.garantir([ip_a])
    assert cert.read_bytes() == antes
    certificado.garantir([ip_b])
    assert cert.read_bytes() != antes

    config = Config()
    config.definir("motor", "backend", "demo")
    optimus = Optimus(config)
    server.Manipulador.estado = server.Estado(optimus)
    manipulador = type("M", (server.Manipulador,), {"senha": ""})
    monkeypatch.setattr("optimus.web.celular.ip_local", lambda: "127.0.0.1")
    servidor = server.ligar_https(config, manipulador, 0)
    try:
        assert servidor is not None
        porta = servidor.server_address[1]
        assert server.endereco_seguro() == f"https://127.0.0.1:{porta}"
        ctx = ssl.create_default_context(cafile=str(cert))
        with urllib.request.urlopen(f"https://127.0.0.1:{porta}/api/estado", timeout=10,
                                    context=ctx) as r:
            assert r.status == 200
    finally:
        server.desligar_https()
    assert server.endereco_seguro() == ""


def test_https_desligado_pela_configuracao():
    config = Config()
    config.definir("web", "https", False)
    assert server.ligar_https(config, server.Manipulador, 0) is None
