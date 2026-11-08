from optimus import config as cfg
from optimus.banco import Banco
from optimus.engine.base import ErroMotor, Motor, Resposta
from optimus.engine.rede import Destino, MotorRede, criar_destino
from optimus.tools.sistema import calcular


def test_config_salva_e_carrega(tmp_path):
    c = cfg.carregar(tmp_path / "c.toml")
    c.definir("voz", "voz", "masculina")
    c.definir("geral", "personalidade", 'Linha 1\nCom "aspas"')
    c.dados["destinos"] = [{"nome": "PC sala", "url": "http://10.0.0.2:11434", "prioridade": 1}]
    c.salvar()
    d = cfg.carregar(tmp_path / "c.toml")
    assert d.get("voz", "voz") == "masculina"
    assert d.get("geral", "personalidade") == 'Linha 1\nCom "aspas"'
    assert d.dados["destinos"][0]["nome"] == "PC sala"
    assert d.get("agente", "modo") == "equilibrado"  # padrão preservado


def test_converter_valor():
    assert cfg.converter_valor("sim") is True and cfg.converter_valor("12") == 12
    assert cfg.converter_valor("0.5") == 0.5 and cfg.converter_valor("qwen3") == "qwen3"


def test_banco_conversas_e_lembretes(tmp_path):
    b = Banco(tmp_path / "b.db")
    cid = b.nova_conversa(projeto="Trabalho")
    b.adicionar_mensagem(cid, "user", "oi")
    b.adicionar_mensagem(cid, "assistant", "olá", {"persona": "optimus"})
    assert [m["conteudo"] for m in b.mensagens(cid)] == ["oi", "olá"]
    assert b.projetos() == ["Trabalho"]
    b.criar_lembrete("água", 0)
    vencido = b.lembretes_vencidos()[0]
    b.concluir_lembrete(vencido)
    assert b.lembretes() == []
    assert {p["chave"] for p in b.personas()} >= {"optimus", "livre"}
    b.apagar_conversa(cid)
    assert b.mensagens(cid) == []


def test_base_de_conhecimento(tmp_path):
    b = Banco(tmp_path / "b.db")
    b.aprender("https://ex.com", "Receita", "Bolo de cenoura leva três cenouras.\nForno 180 graus.")
    achados = b.consultar("quantas cenouras no bolo?")
    assert achados and "cenouras" in achados[0]["trecho"]
    b.esquecer_fonte("https://ex.com")
    assert b.consultar("cenoura") == []


class Falho(Motor):
    def disponivel(self):
        return True

    def conversar(self, *a, **k):
        raise ErroMotor("caiu")


class Bom(Motor):
    def disponivel(self):
        return True

    def conversar(self, mensagens, modelo, *a, **k):
        return Resposta(texto=f"ok {modelo}", modelo=modelo)


class Desligado(Motor):
    def disponivel(self):
        return False


def test_rede_usa_proximo_destino_quando_um_falha():
    rede = MotorRede([Destino("desligado", Desligado(), prioridade=0),
                      Destino("falho", Falho(), prioridade=1),
                      Destino("bom", Bom(), modelo="grande", prioridade=2)])
    resposta = rede.conversar([], "pequeno")
    assert resposta.texto == "ok grande" and rede.ultimo_destino.nome == "bom"


def test_provedor_conhecido_preenche_url():
    d = criar_destino({"backend": "groq", "chave_api": "x"})
    assert "groq.com" in d.motor.url and d.modelo and not d.local


def test_calculadora_segura():
    assert calcular(None, "2^10")["resultado"] == 1024
    assert calcular(None, "sqrt(81) + 1,5")["resultado"] == 10.5
    try:
        calcular(None, "__import__('os').system('ls')")
        assert False
    except ValueError:
        pass
