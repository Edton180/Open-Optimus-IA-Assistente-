"""Testes de regressão dos problemas relatados no primeiro uso real (i3 + qwen3.5:2b)."""

import json
import time

import pytest

from optimus.agent import Agente
from optimus.banco import Banco
from optimus.config import Config
from optimus.engine.base import ChamadaFerramenta, Resposta
from optimus.engine.ollama import MotorOllama
from optimus.roteador import (pre_execucao, roteador_rapido, selecionar_ferramentas,
                              tamanho_modelo)
from optimus.tools import ferramentas_ativas
from tests.ollama_falso import Manipulador, iniciar
from tests.test_agente import MotorRoteiro


def _agente(motor, tmp_path, modelo="qwen3.5:2b", **kw):
    config = Config()
    config.definir("motor", "modelo", modelo)
    config.definir("motor", "modelo_rapido", modelo)
    config.definir("agente", "pasta_trabalho", str(tmp_path))
    config.definir("recursos", "ram_minima_gb", 0)
    return Agente(config=config, motor=motor, banco=Banco(tmp_path / "db.sqlite"), **kw)


@pytest.fixture(scope="module")
def ollama():
    servidor, url = iniciar()
    yield url
    servidor.shutdown()


def test_conversa_comum_nao_manda_ferramentas(tmp_path):
    """Antes: ~40 ferramentas em todo pedido estouravam o contexto de 4096 tokens."""
    motor = MotorRoteiro([Resposta(texto="Oi!")])
    _agente(motor, tmp_path).responder("optimus voz")
    assert motor.ferramentas_recebidas == [[]]


def test_modelo_pequeno_recebe_poucas_ferramentas():
    todas = ferramentas_ativas(Config())
    escolhidas = selecionar_ferramentas("organize a pasta downloads e apague os pdf", todas,
                                        pequeno=True)
    assert 0 < len(escolhidas) <= 6
    assert "criar_lembrete" not in escolhidas and "lembrar" not in escolhidas
    assert tamanho_modelo("qwen3.5:2b") == 2.0 and tamanho_modelo("llama3") == 0


def test_lembrete_sem_pedido_nao_e_criado(tmp_path):
    """Antes: o modelo criava lembretes com o texto do próprio prompt de sistema."""
    motor = MotorRoteiro([
        Resposta(chamadas=[ChamadaFerramenta("criar_lembrete", {"texto": "Fale em português",
                                                                "minutos": 1})]),
        Resposta(texto="ok"),
    ])
    a = _agente(motor, tmp_path)
    assert a.responder("me conte uma piada") == "ok"
    assert a.banco.lembretes() == []


def test_lixo_da_v01_e_limpo(tmp_path):
    banco = Banco(tmp_path / "db.sqlite")
    banco.criar_lembrete("Optimus: Assistente pessoal criado no computador do usuário!", time.time())
    banco.lembrar_fato("Optimus voz! Fale em português do Brasil, educado, direto e com humor!")
    banco.lembrar_fato("Meu time é o Flamengo")
    banco.criar_lembrete("Pagar a conta de luz", time.time() + 60)
    Banco(tmp_path / "db.sqlite")  # reabrir roda a limpeza
    assert [f["texto"] for f in banco.fatos()] == ["Meu time é o Flamengo"]
    assert [lembrete["texto"] for lembrete in banco.lembretes()] == ["Pagar a conta de luz"]


def test_fatos_so_entram_quando_tem_a_ver(tmp_path):
    banco = Banco(tmp_path / "db.sqlite")
    banco.lembrar_fato("Meu time é o Flamengo")
    assert banco.buscar_fatos("me conte uma piada") == []
    assert banco.buscar_fatos("qual é o meu time?") == ["Meu time é o Flamengo"]


def test_lembrete_duplicado_nao_repete(tmp_path):
    banco = Banco(tmp_path / "db.sqlite")
    agora = time.time() + 600
    assert banco.criar_lembrete("beber água", agora) == banco.criar_lembrete("beber água", agora)
    assert banco.cancelar_lembretes() == 1 and banco.lembretes() == []


def test_comandos_diretos():
    assert roteador_rapido("cancelar lembretes") == ("cancelar_lembretes", {})
    assert roteador_rapido("Optimus, mude para a voz Nexus") == ("trocar_voz", {"voz": "nexus"})
    assert roteador_rapido("aumenta o volume") == ("volume", {"acao": "aumentar"})
    assert pre_execucao("pesquise o preço do dólar hoje") == (
        "pesquisar_web", {"consulta": "o preco do dolar hoje"})
    assert pre_execucao("notícias") == ("noticias", {"assunto": "Brasil"})
    assert pre_execucao("me conte uma piada") is None


def test_ollama_streaming_sem_pensamento(ollama, tmp_path):
    """O pedido vai com think=false e a resposta chega em pedaços."""
    Manipulador.pedidos.clear()
    pedacos = []
    motor = MotorOllama(ollama)
    resposta = motor.conversar([{"role": "user", "content": "oi"}], "qwen3.5:2b", None,
                               {"contexto": 4096}, ao_pedaco=pedacos.append)
    assert Manipulador.pedidos[-1]["think"] is False
    assert Manipulador.pedidos[-1]["stream"] is True
    assert len(pedacos) > 10 and "".join(pedacos).strip() == resposta.texto
    assert resposta.tokens_por_segundo == 20.0


def test_agente_real_com_ollama_e_confirmacao(ollama, tmp_path):
    alvo = tmp_path / "lixo.txt"
    alvo.write_text("x")
    eventos = []
    a = _agente(MotorOllama(ollama), tmp_path, confirmar=lambda c, av: False,
                ao_evento=eventos.append)
    resposta = a.responder(f"apague {alvo}")
    assert alvo.exists() and "negou" in resposta
    tipos = [e["tipo"] for e in eventos]
    assert "confirmacao" in tipos and "negada" in tipos and "parcial" in tipos


def test_cancelar_pedido(tmp_path):
    motor = MotorRoteiro([Resposta(texto="nunca chega")])
    a = _agente(motor, tmp_path, cancelado=lambda: True)
    assert a.responder("escreva um livro") == "Pedido cancelado."


def test_trocar_voz_pelo_comando(tmp_path):
    a = _agente(MotorRoteiro([]), tmp_path)
    a.config.caminho = tmp_path / "config.toml"
    resposta = a.responder("Optimus, troque para a voz Valkyrie")
    assert "Valkyrie" in resposta and a.config.get("voz", "voz") == "valkyrie"
    assert json.loads(a.executar_chamada(ChamadaFerramenta("trocar_voz", {"voz": "xyz"})))["erro"]
