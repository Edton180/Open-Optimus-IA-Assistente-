"""Testes das otimizações de velocidade e consumo.

Cobrem o limite de tamanho da resposta (num_predict/max_tokens), que impede respostas
longas de gastar CPU à toa, e a escolha do modelo rápido em PCs fracos.
"""

from optimus.agent import Agente
from optimus.banco import Banco
from optimus.config import Config
from optimus.engine.base import Motor, Resposta
from optimus.engine.ollama import MotorOllama
from optimus.engine.openai_compat import MotorOpenAI


class MotorBobo(Motor):
    def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None,
                  ao_pedaco=None, cancelado=None):
        return Resposta(texto="ok")

    def disponivel(self):
        return True


def _agente(tmp_path, overrides=()):
    config = Config()
    config.definir("motor", "modelo", "principal")
    config.definir("motor", "modelo_rapido", "rapido")
    config.definir("agente", "pasta_trabalho", str(tmp_path))
    for secao, chave, valor in overrides:
        config.definir(secao, chave, valor)
    return Agente(config=config, motor=MotorBobo(), banco=Banco(tmp_path / "db.sqlite"))


# --------------------------------------------------------------- limite de resposta (agente)
def test_voz_limita_resposta(tmp_path):
    a = _agente(tmp_path)
    assert a.opcoes(por_voz=True)["max_resposta"] == 320  # padrão de voz
    assert a.opcoes(por_voz=False)["max_resposta"] == 0   # texto normal: sem limite


def test_economico_limita_resposta_no_texto(tmp_path):
    a = _agente(tmp_path, [("recursos", "uso", "economico")])
    assert a.opcoes(por_voz=False)["max_resposta"] == 768


def test_limite_base_vence_quando_menor(tmp_path):
    a = _agente(tmp_path, [("motor", "max_resposta", 200)])
    # base (200) < voz (320): vence o menor
    assert a.opcoes(por_voz=True)["max_resposta"] == 200
    # base também limita o texto normal
    assert a.opcoes(por_voz=False)["max_resposta"] == 200


def test_maximo_nao_limita_texto(tmp_path):
    a = _agente(tmp_path, [("recursos", "uso", "maximo")])
    assert a.opcoes(por_voz=False)["max_resposta"] == 0


# --------------------------------------------------------------- escolha do modelo
def test_economico_usa_modelo_rapido_em_pergunta_curta(tmp_path):
    # ram_minima_gb=0 evita o desvio por pouca RAM; isola a lógica do modo econômico.
    a = _agente(tmp_path, [("recursos", "uso", "economico"), ("recursos", "ram_minima_gb", 0)])
    assert a.escolher_modelo("que horas são", por_voz=False) == "rapido"


def test_economico_usa_modelo_principal_em_tarefa_pesada(tmp_path):
    a = _agente(tmp_path, [("recursos", "uso", "economico"), ("recursos", "ram_minima_gb", 0)])
    assert a.escolher_modelo("programe um site completo pra mim", por_voz=False) == "principal"


def test_equilibrado_texto_usa_principal(tmp_path):
    a = _agente(tmp_path, [("recursos", "ram_minima_gb", 0)])
    assert a.escolher_modelo("me conte sobre a história de Roma", por_voz=False) == "principal"


# --------------------------------------------------------------- tradução nos motores
def test_ollama_traduz_max_resposta_para_num_predict():
    options, _ = MotorOllama()._opcoes({"max_resposta": 320, "contexto": 4096})
    assert options["num_predict"] == 320
    assert options["num_ctx"] == 4096


def test_ollama_descarta_limite_zero():
    options, _ = MotorOllama()._opcoes({"max_resposta": 0})
    assert "num_predict" not in options


def test_openai_usa_max_tokens():
    corpo = MotorOpenAI()._corpo([{"role": "user", "content": "oi"}], "m",
                                 {"max_resposta": 256, "temperatura": 0.5})
    assert corpo["max_tokens"] == 256
    assert corpo["temperature"] == 0.5


def test_openai_sem_limite_nao_manda_max_tokens():
    corpo = MotorOpenAI()._corpo([{"role": "user", "content": "oi"}], "m", {"max_resposta": 0})
    assert "max_tokens" not in corpo
