"""Testes da palavra de ativação configurável (ferramentas + roteamento)."""

from optimus import config as cfg
from optimus.tools import assistente
from optimus.tools.base import Contexto


def _ctx(tmp_path):
    config = cfg.carregar(tmp_path / "c.toml")
    return Contexto(config=config, banco=None, pasta_trabalho=tmp_path)


def test_definir_e_ver(tmp_path):
    ctx = _ctx(tmp_path)
    assert assistente.palavra_ativacao_ver(ctx)["palavra_ativacao"] == "optimus"  # padrão
    r = assistente.palavra_ativacao_definir(ctx, "Jarvis")
    assert r["palavra_ativacao"] == "jarvis"
    # persistiu no config
    assert ctx.config.get("voz", "palavra_ativacao") == "jarvis"
    assert assistente.palavra_ativacao_ver(ctx)["palavra_ativacao"] == "jarvis"


def test_definir_pega_so_a_primeira_palavra_e_limpa(tmp_path):
    ctx = _ctx(tmp_path)
    r = assistente.palavra_ativacao_definir(ctx, "  Sexta! feira  ")
    assert r["palavra_ativacao"] == "sexta"


def test_definir_curta_demais_erra(tmp_path):
    ctx = _ctx(tmp_path)
    assert "erro" in assistente.palavra_ativacao_definir(ctx, "a")
    assert "erro" in assistente.palavra_ativacao_definir(ctx, "   ")


def test_definir_exige_letras(tmp_path):
    ctx = _ctx(tmp_path)
    assert "erro" in assistente.palavra_ativacao_definir(ctx, "--")   # sem letras
    assert "erro" in assistente.palavra_ativacao_definir(ctx, "7-")   # 0 letras
    # não deve ter persistido nada inválido: continua o padrão
    assert ctx.config.get("voz", "palavra_ativacao", "optimus") == "optimus"


def test_roteamento_expoe_palavra_ativacao():
    from optimus.roteador import selecionar_ferramentas

    disp = {n: object() for n in ("palavra_ativacao_definir", "palavra_ativacao_ver")}
    sel = selecionar_ferramentas("quero te chamar de Jarvis", disp)
    assert "palavra_ativacao_definir" in sel
