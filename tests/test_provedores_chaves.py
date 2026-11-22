"""Novos provedores, IA grátis automática e cofre de chaves."""

import copy

import pytest

from optimus import chaves
from optimus import config as cfg
from optimus.engine import criar_motor
from optimus.engine.base import ErroMotor, Motor, Resposta
from optimus.engine.rede import PROVEDORES, Destino, MotorRede, escolher_modelo


def _config(**motor):
    dados = copy.deepcopy(cfg.PADRAO)
    dados["motor"].update(motor)
    return cfg.Config(dados)


# ------------------------------------------------------------------ provedores
def test_provedores_novos_cadastrados():
    for nome in ("moonshot", "zai", "qwen", "nvidia", "xai", "together", "fireworks",
                 "cerebras", "sambanova", "huggingface", "vllm"):
        assert PROVEDORES[nome]["url"].startswith("http")


def test_escolher_modelo_na_lista_do_provedor():
    assert escolher_modelo(["text-embedding-3", "whisper-1", "meta/llama-x-instruct"]) == \
        "meta/llama-x-instruct"
    assert escolher_modelo(["a/b", "c/d:free"]) == "c/d:free"
    assert escolher_modelo([]) == ""


def test_provedor_na_nuvem_nao_usa_nome_do_ollama():
    motor = criar_motor(_config(backend="groq", chave_api="x", modelo=""))
    assert isinstance(motor, MotorRede)
    destino = motor.destinos[0]
    assert destino.modelo == PROVEDORES["groq"]["modelo"] and not destino.local
    assert destino.ligado()  # provedor único: sempre tenta, não fica "desligado"


def test_provedor_sem_modelo_escolhe_da_lista():
    class Nuvem(Motor):
        def modelos(self):
            return ["embed-1", "kimi-k3-instruct"]

    d = Destino("moonshot", Nuvem(), local=False)
    assert d.modelo_para("qwen3.5:9b") == "kimi-k3-instruct"
    assert Destino("pc", Nuvem(), local=True).modelo_para("qwen3.5:9b") == "qwen3.5:9b"


# ------------------------------------------------------------------ IA grátis automática
class _Limite(Motor):
    def disponivel(self):
        return True

    def conversar(self, *a, **k):
        raise ErroMotor("Servidor respondeu 429: limite gratuito")


class _Bom(Motor):
    def disponivel(self):
        return True

    def conversar(self, mensagens, modelo, *a, **k):
        return Resposta(texto="ok", modelo=modelo)


def test_gratis_so_entra_quem_tem_chave_e_termina_na_ia_local():
    c = _config(backend="gratis")
    c.definir("provedores", "groq_chave", "g")
    c.definir("provedores", "gemini_chave", "")
    c.definir("provedores", "cerebras_chave", "c")
    motor = criar_motor(c)
    assert [d.nome for d in motor.destinos] == ["groq", "cerebras", "IA local"]
    assert motor.destinos[-1].local


def test_gratis_troca_sozinho_quando_bate_no_limite():
    rede = MotorRede([Destino("groq", _Limite(), modelo="a", prioridade=1, local=False),
                      Destino("gemini", _Bom(), modelo="b", prioridade=2, local=False)])
    r = rede.conversar([{"role": "user", "content": "oi"}], "x")
    assert r.texto == "ok" and rede.ultimo_destino.nome == "gemini"
    assert not rede.destinos[0].ligado()  # fica de lado um tempo


# ------------------------------------------------------------------ cofre
class _CofreFalso:
    def __init__(self):
        self.dados = {}

    def get_password(self, s, n):
        return self.dados.get((s, n))

    def set_password(self, s, n, v):
        self.dados[(s, n)] = v

    def delete_password(self, s, n):
        self.dados.pop((s, n))


@pytest.fixture
def cofre(monkeypatch):
    falso = _CofreFalso()
    monkeypatch.setattr(chaves, "_keyring", lambda: falso)
    return falso


def test_referencia_no_config_le_do_cofre(cofre):
    chaves.guardar("motor.chave_api", "segredo-123")
    c = _config(chave_api="cofre:motor.chave_api")
    assert c.get("motor", "chave_api") == "segredo-123"
    assert c.dados["motor"]["chave_api"] == "cofre:motor.chave_api"  # o arquivo não tem a chave


def test_migrar_tira_segredos_do_arquivo(cofre, tmp_path):
    c = _config(chave_api="sk-abc")
    c.caminho = tmp_path / "config.toml"
    c.definir("provedores", "groq_chave", "gsk-1")
    c.dados["destinos"] = [{"nome": "OpenRouter", "chave_api": "or-1"}]
    r = chaves.migrar(c)
    assert r["ok"] and len(r["movidos"]) == 3
    texto = c.caminho.read_text(encoding="utf-8")
    assert "sk-abc" not in texto and "gsk-1" not in texto and "or-1" not in texto
    assert c.get("motor", "chave_api") == "sk-abc"
    assert all(i["no_cofre"] for i in chaves.referencias(c))
    assert chaves.migrar(c)["movidos"] == []  # idempotente


def test_sem_cofre_tudo_continua_funcionando(monkeypatch):
    monkeypatch.setattr(chaves, "_keyring", lambda: None)
    assert not chaves.disponivel()
    assert not chaves.migrar(_config(chave_api="sk"))["ok"]
    assert _config(chave_api="sk-direto").get("motor", "chave_api") == "sk-direto"
    assert chaves.resolver("cofre:x") == ""


def test_cli_chaves_definir(cofre, monkeypatch, capsys):
    from optimus import cli

    assert cli.main(["chaves", "definir", "provedores.groq_chave", "--valor", "gsk-9"]) == 0
    c = cfg.carregar()
    assert c.dados["provedores"]["groq_chave"] == "cofre:provedores.groq_chave"
    assert c.get("provedores", "groq_chave") == "gsk-9"
    assert cli.main(["chaves", "listar"]) == 0
    assert "no cofre" in capsys.readouterr().out
