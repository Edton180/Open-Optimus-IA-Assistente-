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


def test_voltar_desfaz_a_mais_recente_mesmo_com_backup_antigo_de_release(ambiente, monkeypatch):
    config, chamadas = ambiente
    backups = releases._pasta_backups()
    backups.mkdir(parents=True, exist_ok=True)
    (backups / "ultima.json").write_text("{}", encoding="utf-8")  # sobra de uma release antiga
    monkeypatch.setattr(releases, "voltar", lambda: {"ok": True, "via": "release"})
    autoatualizar.registrar_commit(SHA_VELHO)
    assert autoatualizar.baixar(config)["ok"]
    v = autoatualizar.voltar(config)
    assert v.get("via") != "release" and chamadas[-1].endswith(SHA_VELHO)

def test_falha_na_atualizacao_restaura_commit_anterior(ambiente, monkeypatch):
    config, _ = ambiente
    autoatualizar.registrar_commit(SHA_VELHO)
    chamadas = []

    def pip_com_falha_na_nova_versao(url):
        chamadas.append(url)
        if url.endswith(SHA_NOVO):
            return 1, "falha ao resolver dependências"
        return 0, "versão anterior restaurada"

    monkeypatch.setattr(autoatualizar, "_pip", pip_com_falha_na_nova_versao)
    resultado = autoatualizar.baixar(config)

    assert resultado["ok"] is False
    assert resultado["restaurado"] is True
    assert "restaurada" in resultado["erro"]
    assert chamadas[0].endswith(SHA_NOVO)
    assert chamadas[1].endswith(SHA_VELHO)
    assert autoatualizar.commit_instalado() == SHA_VELHO



def test_api_rest_limitada_usa_feed_atom(monkeypatch):
    import httpx

    respostas = [
        httpx.Response(403, request=httpx.Request(
            "GET", "https://api.github.com/repos/exemplo/projeto/commits/main")),
        httpx.Response(200, text="""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>tag:github.com,2008:Grit::Commit/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb</id>
            <title>Correção do atualizador</title>
            <updated>2026-11-24T18:00:00Z</updated>
          </entry>
        </feed>""", request=httpx.Request(
            "GET", "https://github.com/exemplo/projeto/commits/main.atom"))
    ]

    def get(*args, **kwargs):
        return respostas.pop(0)

    monkeypatch.setattr(httpx, "get", get)
    remoto = autoatualizar._commit_remoto_padrao("exemplo/projeto", "main")
    assert remoto["sha"] == SHA_NOVO
    assert remoto["data"] == "2026-11-24"
    assert remoto["titulo"] == "Correção do atualizador"


def test_feed_atom_sem_commit_valido_falha_com_seguranca(monkeypatch):
    import httpx

    respostas = [
        httpx.Response(429, request=httpx.Request(
            "GET", "https://api.github.com/repos/exemplo/projeto/commits/main")),
        httpx.Response(200, text="<feed xmlns='http://www.w3.org/2005/Atom'/>",
                       request=httpx.Request(
                           "GET", "https://github.com/exemplo/projeto/commits/main.atom"))
    ]

    def get(*args, **kwargs):
        return respostas.pop(0)

    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(httpx.HTTPStatusError):
        autoatualizar._commit_remoto_padrao("exemplo/projeto", "main")
