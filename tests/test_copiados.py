"""Testes do histórico de copiados (banco + ferramentas + roteamento)."""

from optimus.banco import Banco
from optimus.tools import copiados as cp
from optimus.tools.base import Contexto


def _banco(tmp_path):
    return Banco(tmp_path / "db.sqlite")


def _ctx(tmp_path):
    return Contexto(config=None, banco=_banco(tmp_path), pasta_trabalho=tmp_path)


# --------------------------------------------------------------- banco
def test_guardar_ignora_vazio_e_repeticao(tmp_path):
    b = _banco(tmp_path)
    assert b.guardar_copiado("   ") is None          # vazio
    assert b.guardar_copiado("oi") is not None
    assert b.guardar_copiado("oi") is None           # igual ao mais recente
    assert len(b.listar_copiados()) == 1


def test_copia_igual_antiga_sobe_para_o_topo(tmp_path):
    b = _banco(tmp_path)
    b.guardar_copiado("a")
    b.guardar_copiado("b")
    b.guardar_copiado("a")  # volta a copiar "a": deve ir para o topo, sem duplicar
    itens = b.listar_copiados()
    assert [i["texto"] for i in itens] == ["a", "b"]


def test_limite_mantem_so_os_ultimos(tmp_path):
    b = _banco(tmp_path)
    for i in range(10):
        b.guardar_copiado(f"item {i}", limite=3)
    itens = b.listar_copiados()
    assert [i["texto"] for i in itens] == ["item 9", "item 8", "item 7"]


def test_apagar_e_limpar(tmp_path):
    b = _banco(tmp_path)
    cid = b.guardar_copiado("x")
    b.guardar_copiado("y")
    assert b.copiado(cid)["texto"] == "x"
    b.apagar_copiado(cid)
    assert b.copiado(cid) is None
    b.limpar_copiados()
    assert b.listar_copiados() == []


# --------------------------------------------------------------- ferramentas
def test_ferramenta_listar(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.banco.guardar_copiado("primeiro")
    ctx.banco.guardar_copiado("segundo")
    r = cp.copiados_listar(ctx, limite=5)
    assert [c["texto"] for c in r["copiados"]] == ["segundo", "primeiro"]


def test_ferramenta_usar_item_inexistente(tmp_path):
    ctx = _ctx(tmp_path)
    assert "erro" in cp.copiado_usar(ctx, id=999)


def test_ferramenta_apagar(tmp_path):
    ctx = _ctx(tmp_path)
    cid = ctx.banco.guardar_copiado("z")
    cp.copiado_apagar(ctx, id=cid)
    assert ctx.banco.copiado(cid) is None


# --------------------------------------------------------------- roteamento
def test_roteamento_expoe_copiados():
    from optimus.roteador import selecionar_ferramentas

    disp = {n: object() for n in (
        "copiados_listar", "copiado_usar", "copiado_apagar", "copiados_limpar")}
    sel = selecionar_ferramentas("mostra meu histórico de copiados", disp)
    assert "copiados_listar" in sel
