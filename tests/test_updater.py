"""Testes do atualizador: operações Git reais em repositórios temporários.

O foco é a barreira de privacidade: nenhum commit automático pode passar com dados
pessoais, e os dados locais do usuário (fora da árvore do Git) nunca são tocados.
"""

import shutil
import subprocess

import pytest

from optimus.updater import Atualizador, ErroGit

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git não instalado")

# Segredos fake montados por partes, para o source não conter um token completo que o
# secret-scanning do GitHub bloquearia. Em tempo de execução testam o regex normalmente.
_SK = "sk-" + "openaistylekey0123456789abcdef"
_GHP = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _repo(tmp_path, nome="repo"):
    repo = tmp_path / nome
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "Teste")
    (repo / "README.md").write_text("# Optimus\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "inicio")
    return repo


def test_detecta_nao_repositorio(tmp_path):
    at = Atualizador(tmp_path)
    assert not at.eh_repositorio()
    with pytest.raises(ErroGit):
        at.estado()


def test_commit_limpo_passa(tmp_path):
    repo = _repo(tmp_path)
    (repo / "novo.py").write_text("def f():\n    return 42\n")
    at = Atualizador(repo)
    r = at.commit("adiciona f")
    assert r["ok"] is True
    assert r["commit"]
    # o arquivo foi de fato commitado
    log = subprocess.run(["git", "-C", str(repo), "log", "--oneline"],
                         capture_output=True, text=True, check=False).stdout
    assert "adiciona f" in log


def test_commit_com_segredo_e_recusado(tmp_path):
    repo = _repo(tmp_path)
    (repo / "vaza.py").write_text(f"OPENAI = '{_SK}'\n")
    at = Atualizador(repo)
    r = at.commit("tenta vazar chave")
    assert r["ok"] is False
    assert r.get("bloqueado_por_privacidade") is True
    # nada foi commitado
    log = subprocess.run(["git", "-C", str(repo), "log", "--oneline"],
                         capture_output=True, text=True, check=False).stdout
    assert "tenta vazar" not in log
    # e o staging foi desfeito (nada preparado)
    porcelain = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True, check=False).stdout
    assert "A  vaza.py" not in porcelain  # não ficou "added/staged"


def test_commit_de_arquivo_proibido_e_recusado(tmp_path):
    repo = _repo(tmp_path)
    (repo / "config.toml").write_text(f'chave_api = "{_SK}"\n')
    at = Atualizador(repo)
    r = at.commit("sobe config")
    assert r["ok"] is False
    assert "config.toml" in r.get("arquivos_bloqueados", [])


def test_commit_sem_mudancas(tmp_path):
    repo = _repo(tmp_path)
    at = Atualizador(repo)
    r = at.commit("nada")
    assert r["ok"] is False
    assert "Não há mudanças" in r["erro"]


def test_commit_mensagem_vazia(tmp_path):
    repo = _repo(tmp_path)
    (repo / "x.py").write_text("x = 1\n")
    at = Atualizador(repo)
    assert at.commit("   ")["ok"] is False


def test_preparar_desfaz_staging_quando_inseguro(tmp_path):
    repo = _repo(tmp_path)
    (repo / "vaza.py").write_text(f"token = '{_GHP}'\n")
    at = Atualizador(repo)
    rel, diff = at.preparar()
    assert not rel.seguro
    assert diff.strip()  # o diff foi inspecionado
    porcelain = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True, check=False).stdout
    assert not porcelain.startswith("A ")  # staging foi resetado


def test_atualizar_ff_only_entre_clones(tmp_path):
    origem = _repo(tmp_path, "origem")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origem), str(clone)], check=True,
                   capture_output=True, text=True)
    # novo commit na origem
    (origem / "extra.py").write_text("y = 2\n")
    _git(origem, "add", "-A")
    _git(origem, "commit", "-q", "-m", "novidade")

    at = Atualizador(clone)
    estado = at.verificar()
    assert estado["atualizado"] is False
    assert estado["atras"] == 1

    r = at.atualizar()
    assert r["ok"] is True and r["mudou"] is True
    assert (clone / "extra.py").exists()


def test_atualizar_recusa_com_mudancas_locais(tmp_path):
    origem = _repo(tmp_path, "origem")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origem), str(clone)], check=True,
                   capture_output=True, text=True)
    (origem / "extra.py").write_text("y = 2\n")
    _git(origem, "add", "-A")
    _git(origem, "commit", "-q", "-m", "novidade")
    # mudança local não salva no clone
    (clone / "README.md").write_text("# mexido localmente\n")

    at = Atualizador(clone)
    r = at.atualizar()
    assert r["ok"] is False
    assert "não salvas" in r["erro"] or "nao salvas" in r["erro"]
