from pathlib import Path

from optimus.config import Config
from optimus.tools import arquivos, sistema
from optimus.tools.base import Contexto


def _ctx(tmp_path):
    return Contexto(config=Config(), pasta_trabalho=tmp_path)


def test_ler_arquivo_pagina_em_blocos_sem_perder_utf8(tmp_path):
    alvo = tmp_path / "grande.txt"
    original = "a" * 65534 + "ç" + "fim"
    alvo.write_text(original, encoding="utf-8")

    primeiro = arquivos.ler_arquivo(_ctx(tmp_path), "grande.txt", limite_bytes=65535)
    segundo = arquivos.ler_arquivo(
        _ctx(tmp_path), "grande.txt", offset=primeiro["proximo_offset"],
        limite_bytes=65536,
    )

    assert primeiro["fim"] is False
    assert primeiro["proximo_offset"] == 65534
    assert primeiro["conteudo"] + segundo["conteudo"] == original
    assert segundo["fim"] is True


def test_escrever_arquivo_publica_arquivo_de_forma_atomica(tmp_path):
    ctx = _ctx(tmp_path)
    resultado = arquivos.escrever_arquivo(ctx, "saida.txt", "conteúdo íntegro")

    assert (tmp_path / "saida.txt").read_text(encoding="utf-8") == "conteúdo íntegro"
    assert resultado["atomico"] is True
    assert not list(tmp_path.glob(".*.optimus-tmp"))


def test_executor_recusa_quinto_comando_concorrente(tmp_path):
    ctx = _ctx(tmp_path)
    adquiridos = 0
    try:
        for _ in range(4):
            assert sistema._COMANDOS_ATIVOS.acquire(blocking=False)
            adquiridos += 1
        resultado = sistema.executar_comando(ctx, "echo teste")
        assert "quatro comandos simultâneos" in resultado["erro"]
    finally:
        for _ in range(adquiridos):
            sistema._COMANDOS_ATIVOS.release()
