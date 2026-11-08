import json

from optimus.agent import Agente, roteador_rapido
from optimus.banco import Banco
from optimus.config import Config
from optimus.engine.base import ChamadaFerramenta, Motor, Resposta, extrair_chamadas_do_texto


class MotorRoteiro(Motor):
    """Devolve respostas pré-definidas e guarda as mensagens recebidas."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.recebidas = []

    def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None):
        self.recebidas.append(list(mensagens))
        return self.respostas.pop(0)

    def disponivel(self):
        return True


def agente(motor, tmp_path, **kw):
    config = Config()
    config.definir("motor", "modelo", "teste")
    config.definir("agente", "pasta_trabalho", str(tmp_path))
    return Agente(config=config, motor=motor, banco=Banco(tmp_path / "db.sqlite"), **kw)


def test_resposta_simples(tmp_path):
    motor = MotorRoteiro([Resposta(texto="Olá!")])
    assert agente(motor, tmp_path).responder("oi") == "Olá!"
    sistema = motor.recebidas[0][0]
    assert sistema["role"] == "system" and "Optimus" in sistema["content"]


def test_usa_ferramenta_e_devolve_resultado(tmp_path):
    (tmp_path / "nota.txt").write_text("segredo do dia: 42", encoding="utf-8")
    motor = MotorRoteiro([
        Resposta(chamadas=[ChamadaFerramenta("ler_arquivo", {"caminho": "nota.txt"})]),
        Resposta(texto="O segredo é 42."),
    ])
    assert agente(motor, tmp_path).responder("leia a nota") == "O segredo é 42."
    resultado = motor.recebidas[1][-1]
    assert resultado["role"] == "tool" and "42" in resultado["content"]


def test_acao_critica_negada_nao_executa(tmp_path):
    alvo = tmp_path / "importante.txt"
    alvo.write_text("x")
    perguntas = []
    motor = MotorRoteiro([
        Resposta(chamadas=[ChamadaFerramenta("apagar", {"caminho": str(alvo)})]),
        Resposta(texto="Ok, não apaguei."),
    ])
    a = agente(motor, tmp_path, confirmar=lambda c, av: perguntas.append(av) or False)
    a.responder("apague")
    assert alvo.exists() and len(perguntas) == 1
    assert "não autorizou" in motor.recebidas[1][-1]["content"]


def test_acao_critica_aprovada_executa(tmp_path):
    alvo = tmp_path / "lixo.txt"
    alvo.write_text("x")
    motor = MotorRoteiro([
        Resposta(chamadas=[ChamadaFerramenta("apagar", {"caminho": str(alvo)})]),
        Resposta(texto="Apaguei."),
    ])
    agente(motor, tmp_path, confirmar=lambda c, av: True).responder("apague")
    assert not alvo.exists()


def test_comando_destrutivo_bloqueado_sem_perguntar(tmp_path):
    perguntas = []
    motor = MotorRoteiro([
        Resposta(chamadas=[ChamadaFerramenta("executar_comando", {"comando": "rm -rf /"})]),
        Resposta(texto="Não posso."),
    ])
    agente(motor, tmp_path, confirmar=lambda c, av: perguntas.append(1) or True).responder("x")
    assert perguntas == []
    assert "bloqueada" in motor.recebidas[1][-1]["content"]


def test_ferramenta_escrita_no_texto(tmp_path):
    texto = 'Vou ver. <tool_call>{"name": "data_hora", "arguments": {}}</tool_call>'
    resto, chamadas = extrair_chamadas_do_texto(texto, {"data_hora"})
    assert chamadas[0].nome == "data_hora" and resto == "Vou ver."
    _, chamadas = extrair_chamadas_do_texto('```json\n{"name":"calcular","arguments":'
                                            '{"expressao":"2+2"}}\n```', {"calcular"})
    assert chamadas[0].argumentos == {"expressao": "2+2"}
    _, nada = extrair_chamadas_do_texto('{"name": "inexistente"}', {"calcular"})
    assert nada == []


def test_modelo_pequeno_que_escreve_a_chamada(tmp_path):
    motor = MotorRoteiro([
        Resposta(texto='{"name": "calcular", "arguments": {"expressao": "6*7"}}'),
        Resposta(texto="Dá 42."),
    ])
    assert agente(motor, tmp_path).responder("quanto é 6x7") == "Dá 42."
    assert json.loads(motor.recebidas[1][-1]["content"])["resultado"] == 42


def test_roteador_rapido_nao_chama_modelo(tmp_path):
    motor = MotorRoteiro([])
    resposta = agente(motor, tmp_path).responder("Optimus, que horas são?")
    assert resposta.startswith("São ") and motor.recebidas == []
    assert roteador_rapido("abre o youtube") == ("abrir", {"alvo": "https://www.youtube.com"})
    assert roteador_rapido("pesquise sobre o youtube") is None


def test_laco_repetido_e_interrompido(tmp_path):
    chamada = lambda: Resposta(chamadas=[ChamadaFerramenta("data_hora", {})])  # noqa: E731
    motor = MotorRoteiro([chamada() for _ in range(4)] + [Resposta(texto="fim")])
    assert agente(motor, tmp_path).responder("hora?") == "fim"
    assert "já chamou" in motor.recebidas[-1][-1]["content"]


def test_memoria_e_conhecimento_entram_no_prompt(tmp_path):
    motor = MotorRoteiro([Resposta(texto="ok")])
    a = agente(motor, tmp_path)
    a.banco.lembrar_fato("O usuário torce para o Flamengo")
    a.banco.aprender("manual", "Manual da cafeteira", "Para limpar a cafeteira use vinagre.")
    a.responder("como limpar a cafeteira? e meu time Flamengo")
    sistema = motor.recebidas[0][0]["content"]
    assert "Flamengo" in sistema and "vinagre" in sistema


def test_persona_troca_prompt_e_modelo(tmp_path):
    motor = MotorRoteiro([Resposta(texto="ok")])
    a = agente(motor, tmp_path)
    persona = {"prompt": "Você é um pirata.", "modelo": "outro-modelo"}
    a.responder("oi", persona=persona)
    assert motor.recebidas[0][0]["content"].startswith("Você é um pirata.")
