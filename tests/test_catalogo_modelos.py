"""Catálogo dinâmico de modelos: JSON atualizável, modelos sem avaliação e teste rápido."""

import json

from optimus import modelos
from optimus.engine.base import Resposta
from optimus.hardware import Hardware, Placa


def _hw(ram=16.0, vram=0.0):
    placa = Placa("nvidia", "RTX", vram) if vram else None
    return Hardware("Linux", "6", "x86_64", "cpu", 4, 8, ram, ram - 2, placa,
                    [placa] if placa else [])


def test_catalogo_embutido_valido():
    dados = json.loads(modelos.ARQUIVO_EMBUTIDO.read_text(encoding="utf-8"))
    assert dados["versao"] > 0
    nomes = [m["nome"] for m in dados["modelos"]]
    assert len(nomes) == len(set(nomes)), "nomes repetidos no catálogo"
    for m in dados["modelos"]:
        assert m["licenca"] and m["laboratorio"] and m["memoria_gb"] > 0
    assert any(m.nome.startswith("gemma4") for m in modelos.CATALOGO)


def test_novidades_nao_sao_recomendadas():
    novos = {m["nome"] for m in modelos.novidades()}
    assert novos, "o catálogo deve ter lançamentos recentes em conferência"
    enorme = _hw(ram=1024, vram=0)
    recomendados = {i["recomendado"]["nome"] for i in modelos.melhores_por_familia(enorme)
                    if i["recomendado"]}
    assert not (novos & recomendados)
    assert not any(m.nome in novos for m in modelos.cabem(1024))


def test_estimar_modelo_desconhecido_pelo_nome():
    e = modelos.estimar("laboratorio-x/novo-modelo:14b-a3b-q8_0")
    assert e["conhecido"] and e["parametros_b"] == 14 and e["ativos_b"] == 3
    assert e["quantizacao"] == "q8" and 14 < e["memoria_gb"] < 18
    gguf = modelos.estimar("hf.co/alguem/Foo-7B-GGUF:Q5_K_M")
    assert gguf["parametros_b"] == 7 and gguf["quantizacao"] == "q5"
    assert modelos.estimar("gemma4:e2b")["parametros_b"] == 2
    assert not modelos.estimar("modelo-sem-tamanho")["conhecido"]


def test_estimar_com_dados_do_ollama():
    info = {"details": {"quantization_level": "Q4_K_M", "parameter_size": "30.5B"},
            "model_info": {"general.parameter_count": 30_532_000_000},
            "capabilities": ["completion", "tools", "thinking"]}
    e = modelos.estimar("qualquer-nome", info)
    assert round(e["parametros_b"]) == 31 and e["quantizacao"] == "q4"
    assert "tools" in e["capacidades"]


def test_cabe_neste_pc():
    assert modelos.cabe_neste_pc("novo:7b", _hw(ram=16))["cabe"]
    grande = modelos.cabe_neste_pc("novo:70b", _hw(ram=16))
    assert not grande["cabe"] and grande["memoria_gb"] > 30
    assert "aviso" in modelos.cabe_neste_pc("sem-tamanho", _hw())
    assert modelos.tamanho("novo:7b") > 0  # fora do catálogo: estimado


def test_atualizar_catalogo_so_aceita_mais_novo_e_valido():
    atual = json.loads(modelos.ARQUIVO_EMBUTIDO.read_text(encoding="utf-8"))
    novo = dict(atual, versao=atual["versao"] + 1,
                modelos=atual["modelos"] + [{"nome": "teste-novo:3b", "familia": "Teste",
                                             "memoria_gb": 2.5, "tipo": "geral",
                                             "descricao": "x", "laboratorio": "L",
                                             "licenca": "MIT", "confirmado": True}])
    velho = dict(atual, versao=1)
    try:
        assert modelos.atualizar_catalogo(baixar=lambda u: json.dumps(velho))["mudou"] is False
        assert not modelos.atualizar_catalogo(baixar=lambda u: '{"modelos": []}')["ok"]
        assert not modelos.atualizar_catalogo(baixar=lambda u: "não é json")["ok"]
        r = modelos.atualizar_catalogo(baixar=lambda u: json.dumps(novo))
        assert r["ok"] and r["mudou"]
        assert any(m.nome == "teste-novo:3b" for m in modelos.CATALOGO)
        assert "Teste" in modelos.familias()
    finally:
        (modelos._arquivo_usuario()).unlink(missing_ok=True)
        modelos.recarregar()
    assert not any(m.nome == "teste-novo:3b" for m in modelos.CATALOGO)


class _MotorFalso:
    def __init__(self, texto="A capital do Brasil é Brasília e 12 vezes 7 são 84."):
        self.texto = texto

    def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None, **_):
        return Resposta(texto=self.texto, modelo=modelo, tokens_por_segundo=21.5)


def test_avaliar_modelo_novo():
    r = modelos.avaliar(_MotorFalso(), "novo:7b")
    assert r["ok"] and r["nota"] == 10 and r["tokens_por_segundo"] == 21.5
    salvo = json.loads((modelos._arquivo_usuario().with_name("avaliacoes.json")).read_text())
    assert "novo:7b" in salvo
    ruim = modelos.avaliar(_MotorFalso("I don't know."), "ruim:1b")
    assert ruim["nota"] < 5


def test_avaliar_motor_quebrado():
    class Quebrado:
        def conversar(self, *a, **k):
            raise RuntimeError("sem memória")

    r = modelos.avaliar(Quebrado(), "x:1b")
    assert not r["ok"] and "sem memória" in r["erro"]
