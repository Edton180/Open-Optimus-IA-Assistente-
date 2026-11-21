"""Testes de hábitos e timers (banco + ferramentas)."""

import datetime as dt
import time

from optimus.banco import Banco
from optimus.tools import produtividade as prod
from optimus.tools.base import Contexto


def _banco(tmp_path):
    return Banco(tmp_path / "db.sqlite")


def _ctx(tmp_path):
    return Contexto(config=None, banco=_banco(tmp_path), pasta_trabalho=tmp_path)


def _dia(delta):
    return (dt.date.today() - dt.timedelta(days=delta)).isoformat()


# --------------------------------------------------------------- hábitos (banco)
def test_criar_habito_nao_duplica(tmp_path):
    b = _banco(tmp_path)
    a = b.criar_habito("Beber água")
    assert b.criar_habito("beber água") == a  # mesmo nome (case-insensitive)
    assert len(b.listar_habitos()) == 1


def test_marcar_habito_idempotente_por_dia(tmp_path):
    b = _banco(tmp_path)
    h = b.criar_habito("Ler")
    assert b.marcar_habito(h) is True
    assert b.marcar_habito(h) is False  # já marcado hoje
    assert b.listar_habitos()[0]["feito_hoje"] is True


def test_sequencia_conta_dias_seguidos(tmp_path):
    b = _banco(tmp_path)
    h = b.criar_habito("Exercício")
    for d in (2, 1, 0):  # anteontem, ontem, hoje
        b.marcar_habito(h, _dia(d))
    assert b.listar_habitos()[0]["sequencia"] == 3


def test_sequencia_quebra_com_buraco(tmp_path):
    b = _banco(tmp_path)
    h = b.criar_habito("Meditar")
    b.marcar_habito(h, _dia(0))   # hoje
    b.marcar_habito(h, _dia(3))   # 3 dias atrás (buraco)
    assert b.listar_habitos()[0]["sequencia"] == 1


def test_sequencia_so_ontem_ainda_conta(tmp_path):
    b = _banco(tmp_path)
    h = b.criar_habito("Correr")
    b.marcar_habito(h, _dia(1))  # só ontem, hoje ainda não
    habito = b.listar_habitos()[0]
    assert habito["sequencia"] == 1
    assert habito["feito_hoje"] is False


def test_desmarcar_e_apagar(tmp_path):
    b = _banco(tmp_path)
    h = b.criar_habito("Água")
    b.marcar_habito(h)
    b.desmarcar_habito(h)
    assert b.listar_habitos()[0]["feito_hoje"] is False
    b.apagar_habito(h)
    assert b.listar_habitos() == []


# --------------------------------------------------------------- timers (banco)
def test_timer_restante_e_vencido(tmp_path):
    b = _banco(tmp_path)
    b.criar_timer("Macarrão", 600)
    ativos = b.listar_timers()
    assert ativos[0]["nome"] == "Macarrão"
    assert 590 <= ativos[0]["restante_seg"] <= 600
    assert ativos[0]["vencido"] is False


def test_timer_vencido_aparece_em_vencidos(tmp_path):
    b = _banco(tmp_path)
    tid = b.criar_timer("Chá", 1)
    time.sleep(1.1)
    vencidos = b.timers_vencidos()
    assert any(t["id"] == tid for t in vencidos)
    b.marcar_timer_tocado(tid)
    assert b.timers_vencidos() == []
    assert b.listar_timers(apenas_ativos=True) == []  # tocado sai dos ativos


def test_cancelar_timer(tmp_path):
    b = _banco(tmp_path)
    tid = b.criar_timer("X", 60)
    b.cancelar_timer(tid)
    assert b.listar_timers(apenas_ativos=False) == []


# --------------------------------------------------------------- ferramentas
def test_ferramentas_habito(tmp_path):
    ctx = _ctx(tmp_path)
    criado = prod.habito_criar(ctx, "Beber água")
    r = prod.habito_marcar(ctx, criado["id"])
    assert r["sequencia"] == 1
    assert prod.habitos_listar(ctx)["habitos"][0]["feito_hoje"] is True


def test_ferramenta_timer_criar_e_listar(tmp_path):
    ctx = _ctx(tmp_path)
    r = prod.timer_criar(ctx, minutos=2, segundos=30, nome="Bolo")
    assert r["duracao_seg"] == 150
    timers = prod.timers_listar(ctx)["timers"]
    assert timers[0]["nome"] == "Bolo"


def test_ferramenta_timer_duracao_invalida(tmp_path):
    ctx = _ctx(tmp_path)
    assert "erro" in prod.timer_criar(ctx, minutos=0, segundos=0)


# --------------------------------------------------------------- roteamento (intenção)
def test_roteamento_expoe_ferramentas_de_timer_e_habito():
    from optimus.roteador import selecionar_ferramentas

    disp = {n: object() for n in (
        "timer_criar", "timers_listar", "timer_cancelar",
        "habito_criar", "habito_marcar", "habitos_listar", "habito_apagar",
        "criar_lembrete", "listar_lembretes", "cancelar_lembretes")}
    timer = selecionar_ferramentas("cria um timer de 10 minutos pro macarrão", disp)
    assert "timer_criar" in timer
    habito = selecionar_ferramentas("quero acompanhar o hábito de beber água", disp)
    assert "habito_criar" in habito


# --------------------------------------------------------------- avisos (timer vencido)
def test_verificar_avisos_toca_timer_vencido(tmp_path):
    from optimus.app import Optimus

    b = _banco(tmp_path)
    b.criar_timer("Chá", 1)
    time.sleep(1.1)
    avisos: list[dict] = []

    class _So:  # self mínimo: _verificar_avisos só usa self.banco
        banco = b

    Optimus._verificar_avisos(_So(), avisos.append)
    assert any(a.get("tipo") == "timer" and "Chá" in a["texto"] for a in avisos)
    assert b.timers_vencidos() == []  # marcado como tocado, não avisa de novo
