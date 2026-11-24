"""Testes de regressão para a inicialização rápida do Optimus."""

import threading

from optimus import app as app_mod
from optimus.config import Config
from optimus.hardware import Hardware


def test_inicializacao_nao_espera_indexacao_de_conhecimento(monkeypatch, tmp_path):
    iniciou = threading.Event()
    liberar = threading.Event()
    instancias = []
    falhas = []

    def indexar_lento(self, base):
        iniciou.set()
        liberar.wait(4)

    monkeypatch.setattr(app_mod.Optimus, "_indexar_conhecimento", indexar_lento)
    monkeypatch.setattr(app_mod.cfg, "pasta_base", lambda: tmp_path)
    monkeypatch.setattr(
        app_mod.hardware,
        "detectar",
        lambda: Hardware("Linux", "teste", "x86_64", "CPU teste", 2, 4, 8, 6),
    )
    monkeypatch.setattr(app_mod, "_baixar_prioridade", lambda: None)

    config = Config()
    config.definir("motor", "backend", "demo")
    config.definir("recursos", "prioridade_baixa", False)

    def construir():
        try:
            instancias.append(app_mod.Optimus(config))
        except Exception as erro:  # noqa: BLE001
            falhas.append(erro)

    thread = threading.Thread(target=construir)
    thread.start()
    assert iniciou.wait(5), "a indexação em segundo plano não foi iniciada"
    thread.join(1)
    terminou_sem_esperar = not thread.is_alive()

    liberar.set()
    thread.join(2)

    assert terminou_sem_esperar, "a inicialização ficou bloqueada esperando a indexação"
    assert not thread.is_alive()
    assert not falhas
    assert len(instancias) == 1
