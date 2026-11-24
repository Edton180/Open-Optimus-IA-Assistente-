import json

from optimus.agent import _resposta_pesquisa_sem_modelo


def test_preserva_resultados_quando_motor_ia_nao_responde():
    bruto = json.dumps({
        "consulta": "ações BRB hoje",
        "itens": [{
            "nome": "BRB Banco de Brasília",
            "trecho": "Resultado sobre ações BSLI3 e BSLI4.",
            "link": "https://ri.brb.com.br/acoes",
            "data": "2026-11-24",
        }],
    }, ensure_ascii=False)
    resposta = _resposta_pesquisa_sem_modelo("pesquisar_web", bruto)
    assert "motor de IA não respondeu" in resposta
    assert "BRB Banco de Brasília" in resposta
    assert "https://ri.brb.com.br/acoes" in resposta


def test_nao_inventa_resultado_quando_busca_falha():
    bruto = json.dumps({"erro": "Nenhum resultado relevante"})
    resposta = _resposta_pesquisa_sem_modelo("pesquisar_web", bruto)
    assert "Nenhum resultado relevante" in resposta
    assert "BRB Banco de Brasília" not in resposta


def test_agente_entrega_links_mesmo_sem_modelo_instalado(tmp_path):
    from optimus.agent import Agente
    from optimus.banco import Banco
    from optimus.config import Config
    from optimus.engine.base import ErroMotor, Motor

    class MotorIndisponivel(Motor):
        def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None):
            raise ErroMotor("Ollama sem modelo instalado")

        def disponivel(self):
            return True

    config = Config()
    config.definir("motor", "modelo", "qwen3.5:2b")
    config.definir("motor", "modelo_rapido", "qwen3.5:2b")
    config.definir("recursos", "ram_minima_gb", 0)
    config.definir("agente", "pasta_trabalho", str(tmp_path))
    agente = Agente(config=config, motor=MotorIndisponivel(),
                    banco=Banco(tmp_path / "agente.sqlite"))
    agente.ferramentas["pesquisar_web"].funcao = lambda ctx, consulta, quantidade=0: {
        "consulta": consulta,
        "itens": [{"nome": "BRB Banco de Brasília", "trecho": "Ações BSLI3 e BSLI4.",
                   "link": "https://ri.brb.com.br/acoes"}],
    }
    resposta = agente.responder("pesquise sobre ações BRB")
    assert "motor de IA não respondeu" in resposta
    assert "https://ri.brb.com.br/acoes" in resposta
