"""Atualização pelo último commit do GitHub (instalação sem Git e sem release nova)."""
from __future__ import annotations

import pytest

from optimus import autoatualizar, releases
from optimus.config import Config

SHA_NOVO = "b" * 40
SHA_VELHO = "a" * 40


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    config = Config({"atualizacao": {"repo": str(tmp_path / "prog"), "ao_iniciar": True}})
    (tmp_path / "prog").mkdir()
    monkeypatch.setattr(releases, "listar", lambda repo: [])  # nenhuma release publicada
    monkeypatch.setattr(autoatualizar, "_commit_remoto",
                        lambda repo, ramo: {"sha": SHA_NOVO, "data": "2026-11-22",
                                            "titulo": "Correções"})
    chamadas = []

    def pip_falso(url):
        chamadas.append(url)
        return 0, "ok"

    monkeypatch.setattr(autoatualizar, "_pip", pip_falso)
    return config, chamadas


def test_sem_release_compara_com_commit_do_github(ambiente):
    config, _ = ambiente
    autoatualizar.registrar_commit(SHA_VELHO)
    info = autoatualizar.verificar(config)
    assert info["modo"] == "github" and info["disponivel"] and not info["atualizado"]
    assert "bbbbbbb" in info["mensagem"] and "aaaaaaa" in info["mensagem"]


def test_ja_atualizado(ambiente):
    config, _ = ambiente
    autoatualizar.registrar_commit(SHA_NOVO)
    info = autoatualizar.verificar(config)
    assert info["atualizado"] and not info["disponivel"]
    assert autoatualizar.automatico(config) is None


def test_baixar_instala_pelo_pip_e_registra(ambiente):
    config, chamadas = ambiente
    autoatualizar.registrar_commit(SHA_VELHO)
    r = autoatualizar.baixar(config)
    assert r["ok"] and r["mudou"]
    assert chamadas and chamadas[0].startswith("optimus-assistente[completo] @ https://codeload")
    assert chamadas[0].endswith(SHA_NOVO)
    assert autoatualizar.commit_instalado() == SHA_NOVO
    # e dá para voltar ao commit anterior
    v = autoatualizar.voltar(config)
    assert v["ok"] and autoatualizar.commit_instalado() == SHA_VELHO
    assert chamadas[-1].endswith(SHA_VELHO)


def test_sem_registro_oferece_baixar(ambiente):
    config, _ = ambiente
    info = autoatualizar.verificar(config)
    assert info["disponivel"] and "Não sei qual versão" in info["mensagem"]


def test_pip_falhou_nao_registra(ambiente, monkeypatch):
    config, _ = ambiente
    autoatualizar.registrar_commit(SHA_VELHO)
    monkeypatch.setattr(autoatualizar, "_pip", lambda url: (1, "erro de rede"))
    r = autoatualizar.baixar(config)
    assert not r["ok"] and "erro de rede" in r["erro"]
    assert autoatualizar.commit_instalado() == SHA_VELHO


def test_sem_internet_da_erro_claro(ambiente, monkeypatch):
    config, _ = ambiente

    def falha(repo, ramo):
        raise OSError("sem rede")

    monkeypatch.setattr(autoatualizar, "_commit_remoto", falha)
    assert "GitHub" in autoatualizar.verificar(config)["erro"]
    assert autoatualizar.automatico(config) is None


def test_automatico_so_avisa_no_modo_github(ambiente):
    config, chamadas = ambiente
    autoatualizar.registrar_commit(SHA_VELHO)
    aviso = autoatualizar.automatico(config)
    assert aviso and aviso["modo"] == "github"
    assert chamadas == []  # nunca instala sozinho por commit


def test_sem_nada_para_desfazer(ambiente):
    config, _ = ambiente
    assert not autoatualizar.voltar(config)["ok"]
