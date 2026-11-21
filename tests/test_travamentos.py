"""Travamentos: um modelo que para de responder não pode prender a tela para sempre."""

import socket
import threading
import time

import httpx
import pytest

from optimus.config import Config
from optimus.engine import criar_motor_principal
from optimus.engine.base import ErroMotor, prazos
from optimus.engine.ollama import MotorOllama
from optimus.engine.openai_compat import MotorOpenAI


def test_prazos_separam_conexao_e_silencio():
    t = prazos(600, 90)
    assert t.connect == 5 and t.read == 90
    assert prazos(600, 0).read == 120  # sem valor: o padrão
    assert prazos(600, 30, conectar=8).connect == 8


def test_configuracao_chega_ao_motor():
    config = Config()
    config.definir("motor", "tempo_sem_resposta", 45)
    motor = criar_motor_principal(config)
    assert isinstance(motor, MotorOllama) and motor.tempo_sem_resposta == 45
    assert Config().get("motor", "tempo_sem_resposta") == 120


def _servidor_mudo(pausa: float):
    """Servidor que aceita o pedido, manda o cabeçalho e um pedaço, e depois fica mudo."""
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen(1)
    porta = sock.getsockname()[1]

    def atender():
        conexao, _ = sock.accept()
        conexao.recv(65536)
        conexao.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\n"
                        b"Transfer-Encoding: chunked\r\n\r\n")
        linha = b'{"message":{"content":"Ol"}}\n'
        conexao.sendall(f"{len(linha):x}\r\n".encode() + linha + b"\r\n")
        time.sleep(pausa)  # travou no meio da resposta
        conexao.close(); sock.close()

    threading.Thread(target=atender, daemon=True).start()
    return f"http://127.0.0.1:{porta}"


def test_ollama_mudo_para_rapido_com_mensagem_clara():
    motor = MotorOllama(_servidor_mudo(pausa=6), tempo_sem_resposta=1)
    pedacos = []
    inicio = time.monotonic()
    with pytest.raises(ErroMotor, match="sem responder"):
        motor.conversar([{"role": "user", "content": "oi"}], "teste", ao_pedaco=pedacos.append)
    assert time.monotonic() - inicio < 4  # antes: até 600 s com a tela parada
    assert pedacos == ["Ol"]  # o que já tinha chegado foi mostrado


def test_cancelar_durante_silencio_nao_vira_erro(monkeypatch):
    def mudo(*_a, **_k):
        raise httpx.ReadTimeout("parado")
    monkeypatch.setattr(httpx, "stream", mudo)
    resposta = MotorOllama().conversar([{"role": "user", "content": "oi"}], "x",
                                       cancelado=lambda: True)
    assert resposta.texto == ""


def test_servidor_openai_mudo_vira_erro_claro(monkeypatch):
    def mudo(*_a, **_k):
        raise httpx.ReadTimeout("parado")
    monkeypatch.setattr(httpx, "stream", mudo)
    with pytest.raises(ErroMotor, match="sem responder"):
        MotorOpenAI("http://127.0.0.1:9/v1").conversar([{"role": "user", "content": "oi"}], "x")
    with pytest.raises(ErroMotor, match="sem responder"):
        list(MotorOpenAI("http://127.0.0.1:9/v1").transmitir([{"role": "user", "content": "oi"}], "x"))
