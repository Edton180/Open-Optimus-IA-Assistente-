"""Testes do destaque de lembretes atrasados (banco + ferramenta)."""

import time

from optimus.banco import Banco
from optimus.tools import memoria
from optimus.tools.base import Contexto


def _banco(tmp_path):
    return Banco(tmp_path / "db.sqlite")


def test_lembrete_vencido_marca_atrasado(tmp_path):
    b = _banco(tmp_path)
    b.criar_lembrete("Pagar luz", time.time() - 60)   # já passou
    b.criar_lembrete("Reunião", time.time() + 3600)    # no futuro
    por_texto = {lem["texto"]: lem for lem in b.lembretes()}
    assert por_texto["Pagar luz"]["atrasado"] is True
    assert por_texto["Pagar luz"]["faltam_seg"] < 0
    assert por_texto["Reunião"]["atrasado"] is False
    assert por_texto["Reunião"]["faltam_seg"] > 0


def test_listar_lembretes_poe_atrasados_primeiro(tmp_path):
    ctx = Contexto(config=None, banco=_banco(tmp_path), pasta_trabalho=tmp_path)
    ctx.banco.criar_lembrete("Futuro", time.time() + 3600)
    ctx.banco.criar_lembrete("Atrasado", time.time() - 120)
    itens = memoria.listar_lembretes(ctx)["itens"]
    assert itens[0]["nome"] == "Atrasado" and itens[0]["atrasado"] is True
    assert itens[1]["nome"] == "Futuro" and itens[1]["atrasado"] is False
