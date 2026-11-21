"""Testes das ferramentas de modelos (optimus/tools/modelos.py).

Cobrem recomendação por hardware, marcação do que está instalado, download (com Ollama
simulado) e a troca do modelo em uso. Não precisam de um Ollama real.
"""

import pytest

from optimus.config import Config
from optimus.tools import modelos as tmod
from optimus.tools.base import Contexto


class MotorFake:
    """Ollama simulado: diz quais modelos estão 'instalados' e registra os baixados."""

    def __init__(self, instalados=(), falha=False):
        self._instalados = list(instalados)
        self.baixados = []
        self.falha = falha

    def modelos(self):
        return sorted(self._instalados)

    def baixar(self, nome, progresso=None):
        if self.falha:
            return False
        self.baixados.append(nome)
        self._instalados.append(nome)
        return True


def _ctx(tmp_path, modelo=""):
    config = Config()
    config.caminho = tmp_path / "config.toml"
    if modelo:
        config.definir("motor", "modelo", modelo)
    return Contexto(config=config, pasta_trabalho=tmp_path)


# --------------------------------------------------------------- recomendação
def test_recomendados_traz_hardware_e_familias(tmp_path):
    dados = tmod._recomendados(_ctx(tmp_path), motor=MotorFake())
    assert dados["recomendado"]  # sempre há um recomendado
    assert isinstance(dados["por_familia"], list) and dados["por_familia"]
    assert "memoria_util_gb" in dados
    # Sem nada instalado, nada está marcado como instalado e há o que baixar.
    assert dados["recomendado_instalado"] is False
    assert dados["nao_instalados"]  # lista do que falta baixar (recomendados por família)


def test_recomendados_marca_instalado(tmp_path):
    rec = tmod._recomendados(_ctx(tmp_path), motor=MotorFake())["recomendado"]
    dados = tmod._recomendados(_ctx(tmp_path), motor=MotorFake(instalados=[rec]))
    assert dados["recomendado_instalado"] is True
    assert rec not in dados["nao_instalados"]


def test_recomendados_sem_ollama_nao_quebra(tmp_path):
    class SemOllama:
        def modelos(self):
            raise ConnectionError("Ollama fechado")

    dados = tmod._recomendados(_ctx(tmp_path), motor=SemOllama())
    assert dados["recomendado"]
    assert dados["recomendado_instalado"] is False  # não deu para listar: tratado como ausente


# --------------------------------------------------------------- download
def test_modelo_baixar_usa_recomendado_quando_vazio(tmp_path, monkeypatch):
    fake = MotorFake()
    monkeypatch.setattr(tmod, "_motor_ollama", lambda ctx: fake)
    resultado = tmod.modelo_baixar(_ctx(tmp_path), "")
    assert resultado["baixado"] in {m.nome for m in tmod.catalogo.CATALOGO}
    assert fake.baixados == [resultado["baixado"]]
    assert resultado["conhecido"] is True


def test_modelo_baixar_nome_fora_do_catalogo_avisa(tmp_path, monkeypatch):
    fake = MotorFake()
    monkeypatch.setattr(tmod, "_motor_ollama", lambda ctx: fake)
    resultado = tmod.modelo_baixar(_ctx(tmp_path), "modelo-inventado:1b")
    assert resultado["baixado"] == "modelo-inventado:1b"
    assert resultado["conhecido"] is False
    assert resultado["aviso"]


def test_modelo_baixar_falha_retorna_erro(tmp_path, monkeypatch):
    monkeypatch.setattr(tmod, "_motor_ollama", lambda ctx: MotorFake(falha=True))
    resultado = tmod.modelo_baixar(_ctx(tmp_path), "qwen3.5:2b")
    assert "erro" in resultado


# --------------------------------------------------------------- trocar modelo
def test_modelo_usar_grava_na_config(tmp_path):
    ctx = _ctx(tmp_path)
    resultado = tmod.modelo_usar(ctx, "qwen3.5:9b")
    assert resultado["usando"] == "qwen3.5:9b"
    assert ctx.config.get("motor", "modelo") == "qwen3.5:9b"


def test_modelo_usar_vazio_pega_recomendado(tmp_path):
    ctx = _ctx(tmp_path)
    resultado = tmod.modelo_usar(ctx, "")
    assert resultado["usando"]
    assert ctx.config.get("motor", "modelo") == resultado["usando"]


def test_modelo_usar_sem_config_erro():
    resultado = tmod.modelo_usar(Contexto(config=None), "qwen3.5:2b")
    assert "erro" in resultado
