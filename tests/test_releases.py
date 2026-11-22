"""Atualização por releases do GitHub: decisão (sem rede), instalação segura e voltar."""

import hashlib
import io
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from optimus import releases
from optimus.releases import Politica, Release, Versao, decidir, dentro_da_janela

AGORA = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)


def _rel(tag, dias=10, pre=False, draft=False, assets=None):
    return Release(tag=tag, versao=Versao.ler(tag), publicada=AGORA - timedelta(days=dias),
                   prerelease=pre, draft=draft, assets=assets or {})


# ------------------------------------------------------------------ versões
def test_ordem_das_versoes():
    assert Versao.ler("v0.2.0") > Versao.ler("0.1.9")
    assert Versao.ler("1.0.0-beta.2") < Versao.ler("1.0.0")
    assert Versao.ler("1.0.0-beta.2") > Versao.ler("1.0.0-beta.1")
    assert Versao.ler("1.10") > Versao.ler("1.9.9")
    assert str(Versao.ler("v2")) == "2.0.0"
    with pytest.raises(ValueError):
        Versao.ler("ultima")


def test_release_da_api_ignora_tag_que_nao_e_versao():
    assert Release.de_api({"tag_name": "nightly"}) is None
    r = Release.de_api({"tag_name": "v0.3.0", "published_at": "2026-11-01T10:00:00Z",
                        "assets": [{"name": "optimus-v0.3.0.zip",
                                    "browser_download_url": "https://x/z.zip"}]})
    assert r.versao == Versao(0, 3, 0) and r.pacote() == ("optimus-v0.3.0.zip", "https://x/z.zip")


# ------------------------------------------------------------------ decisão
def test_ja_atualizado():
    d = decidir("0.3.0", [_rel("v0.3.0"), _rel("v0.2.0")], Politica(), AGORA)
    assert not d.disponivel and d.motivo == "atualizado"


def test_rascunho_e_beta_fora_do_canal_estavel():
    lista = [_rel("v0.4.0", draft=True), _rel("v0.5.0-beta.1", pre=True), _rel("v0.3.0")]
    assert str(decidir("0.1.0", lista, Politica(), AGORA).alvo.versao) == "0.3.0"
    assert str(decidir("0.1.0", lista, Politica(canal="beta"), AGORA).alvo.versao) == "0.5.0-beta.1"


def test_versao_maior_sempre_pede_confirmacao():
    d = decidir("0.9.0", [_rel("v1.0.0")], Politica(automatico=True, espera_horas=0), AGORA)
    assert d.motivo == "versao_maior" and d.pede_confirmacao and not d.instalar_sozinho


def test_espera_depois_de_publicada():
    d = decidir("0.1.0", [_rel("v0.2.0", dias=1)], Politica(automatico=True, espera_horas=48),
                AGORA)
    assert d.motivo == "aguardando" and not d.instalar_sozinho and d.disponivel


def test_automatico_so_com_permissao():
    lista = [_rel("v0.2.0")]
    assert not decidir("0.1.0", lista, Politica(), AGORA).instalar_sozinho
    assert decidir("0.1.0", lista, Politica(automatico=True), AGORA).instalar_sozinho


def test_janela_de_horario():
    t = datetime(2026, 1, 1, 23, 30)
    assert dentro_da_janela(t, "22:00-03:00")
    assert not dentro_da_janela(t, "02:00-05:00")
    assert dentro_da_janela(datetime(2026, 1, 1, 2, 30), "22:00-03:00")
    assert dentro_da_janela(t, "")  # vazio = qualquer hora
    assert dentro_da_janela(t, "lixo-xx")  # mal escrito não bloqueia


# ------------------------------------------------------------------ instalar / voltar
def _zip(versao="0.2.0", extra=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"optimus-v{versao}/optimus/__init__.py", f'__version__ = "{versao}"\n')
        z.writestr(f"optimus-v{versao}/optimus/novo.py", "X = 1\n")
        z.writestr(f"optimus-v{versao}/README.md", "fora do pacote\n")
        for nome, conteudo in (extra or {}).items():
            z.writestr(nome, conteudo)
    return buf.getvalue()


def _programa(tmp_path):
    pasta = tmp_path / "site"
    (pasta / "optimus").mkdir(parents=True)
    (pasta / "optimus" / "__init__.py").write_text('__version__ = "0.1.0"\n')
    (pasta / "optimus" / "velho.py").write_text("Y = 2\n")
    return pasta


def _release_com(conteudo, soma=None):
    assets = {"optimus-v0.2.0.zip": "u://zip", "SHA256SUMS": "u://somas"}
    arquivos = {"u://zip": conteudo,
                "u://somas": f"{soma or hashlib.sha256(conteudo).hexdigest()}  "
                             "optimus-v0.2.0.zip\n".encode()}
    return _rel("v0.2.0", assets=assets), arquivos.__getitem__


def test_instala_confere_soma_e_volta(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMUS_HOME", str(tmp_path / "home"))
    pasta = _programa(tmp_path)
    rel, baixar = _release_com(_zip())
    r = releases.instalar(rel, pasta, "0.1.0", baixar=baixar)
    assert r["ok"] and r["versao"] == "0.2.0"
    assert (pasta / "optimus" / "novo.py").exists()
    assert not (pasta / "optimus" / "velho.py").exists()
    assert not (pasta / "README.md").exists()  # só a pasta do pacote é trocada
    v = releases.voltar()
    assert v["ok"] and v["versao"] == "0.1.0"
    assert (pasta / "optimus" / "velho.py").exists()
    assert not (pasta / "optimus" / "novo.py").exists()
    assert not releases.voltar()["ok"]  # nada mais para desfazer


def test_soma_errada_nao_mexe_em_nada(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMUS_HOME", str(tmp_path / "home"))
    pasta = _programa(tmp_path)
    rel, baixar = _release_com(_zip(), soma="0" * 64)
    with pytest.raises(releases.ErroRelease, match="SHA-256"):
        releases.instalar(rel, pasta, "0.1.0", baixar=baixar)
    assert (pasta / "optimus" / "velho.py").exists()


def test_sem_somas_publicadas_recusa(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMUS_HOME", str(tmp_path / "home"))
    rel = _rel("v0.2.0", assets={"optimus-v0.2.0.zip": "u://zip"})
    with pytest.raises(releases.ErroRelease, match="SHA256SUMS"):
        releases.instalar(rel, _programa(tmp_path), "0.1.0", baixar=lambda u: _zip())


def test_zip_slip_bloqueado(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMUS_HOME", str(tmp_path / "home"))
    pasta = _programa(tmp_path)
    ruim = _zip(extra={"optimus-v0.2.0/optimus/../../fora.py": "mal = 1\n"})
    rel, baixar = _release_com(ruim)
    with pytest.raises(releases.ErroRelease, match="suspeito"):
        releases.instalar(rel, pasta, "0.1.0", baixar=baixar)
    assert not (tmp_path / "fora.py").exists()


# ------------------------------------------------------------------ ponto único
def test_autoatualizar_sem_git_usa_releases(tmp_path, monkeypatch):
    from optimus import autoatualizar
    from optimus.config import Config

    monkeypatch.setenv("OPTIMUS_HOME", str(tmp_path / "home"))
    config = Config({"atualizacao": {"repo": str(tmp_path), "ao_iniciar": True}})
    monkeypatch.setattr(releases, "listar", lambda repo: [_rel("v99.0.0")])
    info = autoatualizar.verificar(config)
    assert info["modo"] == "release" and info["motivo"] == "versao_maior"
    aviso = autoatualizar.automatico(config)
    assert aviso and aviso["pede_confirmacao"]  # só avisa, não instala versão maior


def test_cli_atualizar_verificar(tmp_path, monkeypatch, capsys):
    from optimus import autoatualizar, cli

    monkeypatch.setattr(autoatualizar, "verificar",
                        lambda c: {"mensagem": "tudo certo", "atualizado": True})
    assert cli.main(["atualizar", "--verificar"]) == 0
    assert "tudo certo" in capsys.readouterr().out
