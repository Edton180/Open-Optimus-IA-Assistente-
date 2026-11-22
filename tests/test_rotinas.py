"""Testes de rotinas (banco + ferramentas + roteamento)."""

from optimus.banco import Banco
from optimus.tools import rotinas as rt
from optimus.tools.base import Contexto


def _banco(tmp_path):
    return Banco(tmp_path / "db.sqlite")


def _ctx(tmp_path):
    return Contexto(config=None, banco=_banco(tmp_path), pasta_trabalho=tmp_path)


# --------------------------------------------------------------- banco
def test_criar_guarda_passos_em_ordem(tmp_path):
    b = _banco(tmp_path)
    b.criar_rotina("Bom dia", ["resumo do dia", "previsão do tempo", "tocar playlist"])
    r = b.rotina_por_nome("bom dia")  # case-insensitive
    assert r["passos"] == ["resumo do dia", "previsão do tempo", "tocar playlist"]


def test_recriar_mesmo_nome_regrava_passos(tmp_path):
    b = _banco(tmp_path)
    b.criar_rotina("Noite", ["apagar luzes", "despertador 7h"])
    b.criar_rotina("noite", ["trancar portão"])  # mesmo nome: regrava
    assert len(b.listar_rotinas()) == 1
    assert b.rotina_por_nome("noite")["passos"] == ["trancar portão"]


def test_passos_vazios_sao_ignorados(tmp_path):
    b = _banco(tmp_path)
    b.criar_rotina("X", ["  ", "faz algo", ""])
    assert b.rotina_por_nome("x")["passos"] == ["faz algo"]


def test_apagar_leva_os_passos(tmp_path):
    b = _banco(tmp_path)
    rid = b.criar_rotina("Y", ["um", "dois"])
    b.apagar_rotina(rid)
    assert b.listar_rotinas() == []
    # a cascata apagou os passos
    assert b._todos("SELECT * FROM rotina_passos") == []


# --------------------------------------------------------------- ferramentas
def test_ferramenta_criar_aceita_lista(tmp_path):
    ctx = _ctx(tmp_path)
    r = rt.rotina_criar(ctx, "Treino", ["aquecer", "correr", "alongar"])
    assert r["passos"] == ["aquecer", "correr", "alongar"]


def test_ferramenta_criar_aceita_texto_com_linhas(tmp_path):
    ctx = _ctx(tmp_path)
    r = rt.rotina_criar(ctx, "Estudo", "ler capítulo; fazer exercícios\nrevisar")
    assert r["passos"] == ["ler capítulo", "fazer exercícios", "revisar"]


def test_ferramenta_criar_sem_passos_erra(tmp_path):
    ctx = _ctx(tmp_path)
    assert "erro" in rt.rotina_criar(ctx, "Vazia", [])


def test_ferramenta_executar_devolve_passos(tmp_path):
    ctx = _ctx(tmp_path)
    rt.rotina_criar(ctx, "Sair", ["apagar luzes", "trancar porta"])
    r = rt.rotina_executar(ctx, "sair")
    assert r["passos"] == ["apagar luzes", "trancar porta"]


def test_ferramenta_executar_inexistente(tmp_path):
    ctx = _ctx(tmp_path)
    assert "erro" in rt.rotina_executar(ctx, "não existe")


# --------------------------------------------------------------- roteamento
def test_roteamento_expoe_rotinas():
    from optimus.roteador import selecionar_ferramentas

    disp = {n: object() for n in (
        "rotina_criar", "rotinas_listar", "rotina_executar", "rotina_apagar")}
    sel = selecionar_ferramentas("cria uma rotina chamada bom dia", disp)
    assert "rotina_criar" in sel
