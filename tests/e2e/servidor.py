"""Servidor isolado para E2E do painel Casa; não toca no Docker real do runner."""
from optimus.app import Optimus
from optimus.engine.demo import MotorDemo
from optimus.smart_home import home_assistant as ha
from optimus.web import server


def estado_fake():
    return {
        "runtime": {"sistema": "Linux", "suportado": True, "docker_instalado": True,
                    "docker_ativo": True, "docker_versao": "test", "observacao": ""},
        "container": {"instalado": False, "estado": "nao_instalado", "rodando": False},
        "tarefa": dict(ha._TAREFA), "acoes": list(ha._TAREFA.get("acoes", [])),
        "url": "", "dados": "/tmp/optimus/home_assistant",
        "nota": "Home Assistant Container de teste."
    }


def acao_fake(nome):
    ha._TAREFA.setdefault("acoes", []).append(nome)
    ha._TAREFA.update(estado="concluido", mensagem="Operação simulada com sucesso.",
                      erro="", atualizado=0.0)
    return {"ok": True, "mensagem": "Operação simulada com sucesso."}


ha.estado = estado_fake
ha.executar_acao = acao_fake
optimus = Optimus()
optimus.motor = MotorDemo()
server.iniciar(host="127.0.0.1", porta=8765, abrir_navegador=False, optimus=optimus)
