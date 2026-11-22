"""Estúdio, paridade: OmniVoice, Piper, servidor remoto, modelos, desempenho, marcas de
expressão, receitas, pastas observadas e servidor MCP."""

import io
import json
import sys
import types
from pathlib import Path

import pytest

from optimus.estudio import (
    automacao,
    desempenho,
    expressao,
    idiomas,
    modelos,
    motores,
    omnivoice,
    piper,
    remoto,
    vozes,
)
from optimus.estudio.audio import ErroEstudio

np = pytest.importorskip("numpy")


class _Config:
    def __init__(self, **estudio):
        self.dados = {"estudio": dict(estudio)}
        self.salvo = False

    def get(self, secao, chave, padrao=None):
        return self.dados.get(secao, {}).get(chave, padrao)

    def definir(self, secao, chave, valor):
        self.dados.setdefault(secao, {})[chave] = valor

    def salvar(self):
        self.salvo = True


@pytest.fixture
def omni_falso(monkeypatch):
    """Um pacote `omnivoice` de mentira que registra o que foi pedido."""
    chamadas = {"generate": [], "prompts": 0}

    class Prompt:
        def save(self, caminho):
            Path(caminho).write_bytes(b"p")

        @staticmethod
        def load(caminho):
            return Prompt()

    class Modelo:
        @classmethod
        def from_pretrained(cls, *a, **k):
            return cls()

        def create_voice_clone_prompt(self, **k):
            chamadas["prompts"] += 1
            return Prompt()

        def generate(self, **k):
            chamadas["generate"].append(k)
            segundos = k.get("duration") or 0.5
            return [np.full(int(24000 * segundos), 0.2, dtype="float32")]

    modulo = types.ModuleType("omnivoice")
    modulo.OmniVoice = Modelo
    modulo.VoiceClonePrompt = Prompt
    monkeypatch.setitem(sys.modules, "omnivoice", modulo)
    monkeypatch.setattr(omnivoice, "instalado", lambda: True)
    monkeypatch.setattr(omnivoice, "_dispositivo", lambda: ("cpu", "float32"))
    omnivoice.descarregar()
    yield chamadas
    omnivoice.descarregar()


# ------------------------------------------------------------------ OmniVoice
def test_descricao_vira_atributos_do_omnivoice():
    assert omnivoice.instrucao("voz feminina idosa, grave e sussurrando") == \
        "female, elderly, low pitch, whisper"
    assert omnivoice.instrucao("sotaque britânico", "masculina") == "male, british accent"
    assert omnivoice.converter_sons("Oi [risada] tudo [Suspiro] [desconhecido]") == \
        "Oi [laughter] tudo [sigh] [desconhecido]"


def test_voz_criada_pelo_omnivoice_usa_a_instrucao(omni_falso):
    p = vozes.criar("Avó", "voz feminina idosa e calma")
    assert p.motor == "omnivoice" and "elderly" in p.instrucao
    x = motores.gerar("Olá, netinho.", p)
    pedido = omni_falso["generate"][0]
    assert pedido["instruct"].startswith("female") and "ref_audio" not in pedido
    assert x.dtype == np.float32 and len(x) > 0
    ajustada = vozes.criar("Robô", "robótica", motor="ajustes")
    assert ajustada.motor == "padrao" and ajustada.efeito == "cyber"


def test_clonagem_pelo_omnivoice_guarda_a_impressao_e_respeita_a_duracao(omni_falso, monkeypatch):
    monkeypatch.setattr(motores, "chatterbox_instalado", lambda: False)
    p = vozes.Perfil("eu", "Eu", "clonada", "clone", amostra="amostra.wav")
    (vozes.pasta_vozes() / "eu").mkdir(parents=True)
    amostra = vozes.pasta_vozes() / "eu" / "amostra.wav"
    amostra.write_bytes(b"RIFF")
    assert motores.motor_clone(idiomas.idioma("uk")) == "omnivoice"
    motores.gerar("Привіт усім.", p, "uk", duracao=2.0)
    motores.gerar("Ще раз.", p, "uk")
    assert omni_falso["prompts"] == 1  # a impressão da voz é calculada uma vez só
    assert amostra.with_suffix(".omnivoice.pt").exists()
    primeiro = omni_falso["generate"][0]
    assert "voice_clone_prompt" in primeiro and primeiro["duration"] == pytest.approx(2.0)


def test_escolha_do_motor_de_clonagem(monkeypatch):
    pt, sw = idiomas.idioma("pt-BR"), idiomas.idioma("qu")
    monkeypatch.setattr(motores, "chatterbox_instalado", lambda: True)
    monkeypatch.setattr(omnivoice, "instalado", lambda: True)
    assert motores.motor_clone(pt) == "chatterbox"
    assert motores.motor_clone(sw) == "omnivoice"  # o Chatterbox não fala quíchua
    assert motores.motor_clone(pt, _Config(motor_clone="omnivoice")) == "omnivoice"
    monkeypatch.setattr(motores, "chatterbox_instalado", lambda: False)
    monkeypatch.setattr(omnivoice, "instalado", lambda: False)
    assert motores.motor_clone(pt, _Config(servidor_voz_url="http://x/v1")) == "remoto"
    with pytest.raises(ErroEstudio, match="omnivoice"):
        motores.motor_clone(pt)


# ------------------------------------------------------------------ expressão
def test_marcas_de_pausa_e_som():
    assert expressao.partes("Oi. [pausa 1,5] Tudo? [pausa] Fim") == \
        [("Oi.", 1.5), ("Tudo?", expressao.PAUSA_PADRAO), ("Fim", 0.0)]
    assert expressao.partes("[pausa 99s]") == [("", 10.0)]
    assert expressao.sem_sons("Que bom [risada] [nome]") == "Que bom [nome]"
    assert expressao.tem_som("ah [suspiro]") and not expressao.tem_som("[pausa 2]")


def test_pausa_vira_silencio_no_audio(monkeypatch):
    feitos = []

    def falso(texto, perfil, velocidade, config):
        feitos.append(texto)
        return np.full(24000, 0.3, dtype="float32")

    monkeypatch.setattr(motores, "_gerar_padrao", falso)
    x = motores.gerar("Primeiro. [pausa 2] Segundo [risada].", "Prime")
    assert feitos == ["Primeiro.", "Segundo ."] or feitos == ["Primeiro.", "Segundo."]
    assert len(x) >= 24000 * 3.9  # 1 s + 2 s de silêncio + 1 s
    meio = x[int(24000 * 1.5): int(24000 * 2.5)]
    assert np.max(np.abs(meio)) < 0.01


# ------------------------------------------------------------------ Piper
def test_piper_baixa_e_gera_em_portugues(monkeypatch):
    baixados = []

    class Tts:
        def generate(self, texto, sid, speed):
            return types.SimpleNamespace(samples=[0.1] * 22050, sample_rate=22050)

    monkeypatch.setattr(piper, "baixada", lambda v: bool(baixados))
    monkeypatch.setattr(piper, "baixar", lambda i, p=None: baixados.append(i))
    monkeypatch.setattr(piper, "_motor", lambda v: Tts())
    monkeypatch.setattr(piper, "instalado", lambda: True)
    faber = vozes.obter("Faber (Piper)")
    assert faber.motor == "piper" and faber.idioma == "pt-BR"
    x = motores.gerar("Olá, eu sou o Faber.", faber)
    assert baixados == ["pt_BR-faber-medium"] and len(x) > 20000
    with pytest.raises(ErroEstudio):
        piper.voz("xx_XX-ninguem")


# ------------------------------------------------------------------ servidor remoto
def test_servidor_remoto_fala_e_transcreve(monkeypatch, tmp_path):
    import httpx

    from optimus.estudio import audio, transcrever

    pedidos = []

    def post(url, **k):
        pedidos.append((url, k))
        if url.endswith("/audio/speech"):
            return httpx.Response(200, content=audio.wav_bytes(np.zeros(2400, "float32"), 24000),
                                  headers={"content-type": "audio/wav"},
                                  request=httpx.Request("POST", url))
        return httpx.Response(200, json={"language": "portuguese", "segments": [
            {"start": 0, "end": 1.5, "text": " Olá mundo "}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    config = _Config(servidor_voz_url="http://gpu:8000", servidor_voz_chave="segredo",
                     servidor_voz_voz="nova")
    x, taxa = remoto.falar("Oi", config=config)
    assert taxa == 24000 and len(x) == 2400
    url, k = pedidos[0]
    assert url == "http://gpu:8000/v1/audio/speech" and k["json"]["voice"] == "nova"
    assert k["headers"]["Authorization"] == "Bearer segredo"
    midia = tmp_path / "a.wav"
    midia.write_bytes(b"x")
    trechos, falado = transcrever.transcrever(midia, config=config, motor="remoto")
    assert trechos[0].texto == "Olá mundo" and falado.codigo == "pt-BR"
    with pytest.raises(ErroEstudio, match="servidor_voz_url"):
        remoto.falar("Oi", config=_Config())


# ------------------------------------------------------------------ modelos e desempenho
def test_gerenciador_de_modelos_lista_e_remove(monkeypatch):
    itens = {m["id"]: m for m in modelos.listar()}
    for ident in ("omnivoice", "chatterbox", "piper-pt_BR-faber-medium", "whisper-medium",
                  "quem-fala", "demucs"):
        assert ident in itens and itens[ident]["licenca"]
    assert itens["piper-pt_BR-faber-medium"]["licenca"] == "CC0"
    v = piper.voz("pt_BR-faber-medium")
    piper.pasta_voz(v).mkdir(parents=True)
    (piper.pasta_voz(v) / "pt_BR-faber-medium.onnx").write_bytes(b"0" * 2048)
    assert modelos.obter("piper-pt_BR-faber-medium").instalado()
    modelos.remover("piper-pt_BR-faber-medium")
    assert not piper.pasta_voz(v).exists()
    pip = []
    monkeypatch.setattr(modelos, "_pip", lambda *a: pip.append(a) or "")
    modelos.instalar("omnivoice")
    modelos.remover("sherpa-onnx")
    assert pip == [("install", "omnivoice"), ("uninstall", "-y", "sherpa-onnx")]
    with pytest.raises(ErroEstudio):
        modelos.obter("nao-existe")


def test_predefinicoes_de_desempenho(monkeypatch):
    monkeypatch.setattr(desempenho, "recomendar", lambda: "rapido")
    assert desempenho.atual(_Config()).nome == "rapido"
    config = _Config()
    assert desempenho.escolher(config, "Qualidade").transcricao == "large-v3-turbo"
    assert config.salvo and config.dados["estudio"]["desempenho"] == "qualidade"
    with pytest.raises(ValueError):
        desempenho.escolher(config, "turbo")
    from optimus.estudio import transcrever

    assert transcrever.modelo_padrao(_Config(desempenho="rapido")) == "small"
    assert transcrever.modelo_padrao(_Config(modelo_transcricao="tiny")) == "tiny"


def test_idiomas_alem_dos_principais():
    todos = idiomas.todos()
    assert len(todos) > 90 and todos[0].codigo == "pt-BR"
    assert idiomas.idioma("ucraniano").whisper == "uk"
    assert idiomas.idioma("qu").codigo == "qu"


# ------------------------------------------------------------------ receitas e pastas
def test_receitas_salvar_apagar_e_aplicar(monkeypatch, tmp_path):
    assert any(r.nome == "Dublar para português" for r in automacao.receitas())
    r = automacao.salvar_receita("Inglês com Mordomo", "dublar",
                                 {"idioma": "en-US", "voz": "Mordomo", "arquivo": "x"})
    assert r.acao == "estudio_dublar" and "arquivo" not in r.opcoes
    with pytest.raises(ErroEstudio):
        automacao.salvar_receita("Ruim", "apagar_tudo")
    from optimus.tools.base import registradas

    chamado = {}
    ferr = registradas()["estudio_dublar"]
    monkeypatch.setattr(ferr, "funcao", lambda ctx, **k: chamado.update(k) or {"tarefa": "1"})
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    assert automacao.aplicar("inglês com", video) == {"tarefa": "1"}
    assert chamado["idioma"] == "en-US" and chamado["arquivo"] == str(video.resolve())
    assert automacao.apagar_receita("Inglês com Mordomo")
    assert not automacao.apagar_receita("Inglês com Mordomo")


def test_pasta_observada_so_pega_arquivos_novos_e_completos(monkeypatch, tmp_path):
    pasta = tmp_path / "entrada"
    pasta.mkdir()
    (pasta / "antigo.mp4").write_bytes(b"velho")
    automacao.observar(pasta, "Transcrever")
    feitos = []
    monkeypatch.setattr(automacao, "aplicar", lambda receita, f, config=None:
                        feitos.append((receita, f.name)) or {"ok": True})
    obs = automacao.Observador()
    (pasta / "novo.mp3").write_bytes(b"123")
    (pasta / "nota.xyz").write_bytes(b"1")
    assert obs.uma_vez() == []  # primeira olhada: espera o arquivo parar de crescer
    assert len(obs.uma_vez()) == 1
    assert obs.uma_vez() == []  # já processado
    assert feitos == [("Transcrever", "novo.mp3")]
    assert automacao.parar_de_observar(pasta) and not automacao.observadas()
    with pytest.raises(ErroEstudio):
        automacao.observar(tmp_path / "nao-existe", "Transcrever")


# ------------------------------------------------------------------ servidor MCP
def test_servidor_mcp_lista_e_chama_ferramentas_do_estudio():
    from optimus.mcp_servidor import Servidor

    s = Servidor(_Config())
    entrada = io.StringIO("\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-03-26"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "pronuncia_adicionar",
                    "arguments": {"escrito": "Kaik", "falado": "Káique"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "estudio_clonar_voz", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "nada"},
    ]) + "\nnão é json\n")
    saida = io.StringIO()
    s.rodar(entrada, saida)
    respostas = [json.loads(linha) for linha in saida.getvalue().splitlines()]
    assert [r.get("id") for r in respostas] == [1, 2, 3, 4, 5, None]
    assert respostas[0]["result"]["protocolVersion"] == "2025-03-26"
    nomes = {t["name"] for t in respostas[1]["result"]["tools"]}
    assert {"estudio_falar", "estudio_dublar", "estudio_legendar"} <= nomes
    assert "estudio_clonar_voz" not in nomes  # clonar só pelo próprio Optimus
    assert all(t["inputSchema"]["type"] == "object" for t in respostas[1]["result"]["tools"])
    assert respostas[2]["result"]["isError"] is False
    assert respostas[3]["result"]["isError"] is True
    assert respostas[4]["error"]["code"] == -32601 and respostas[5]["error"]["code"] == -32700
    so_livres = Servidor(_Config(), moderadas=False)
    assert "estudio_dublar" not in so_livres.ferramentas


# ------------------------------------------------------------------ tela (API)
def test_api_modelos_receitas_e_observar(tmp_path):
    from tests.test_estudio_parte2 import _api

    st, r = _api("GET", "modelos")
    assert st == 200 and r["modelos"] and r["atual"]["nome"] in desempenho.PREDEFINICOES
    st, r = _api("POST", "desempenho", {"escolha": "rapido"})
    assert st == 200 and r["atual"]["nome"] == "rapido"
    st, r = _api("POST", "receitas", {"nome": "Só voz", "acao": "separar_voz", "opcoes": ""})
    assert st == 200 and r["receita"]["acao"] == "estudio_separar_voz"
    st, r = _api("GET", "receitas")
    assert any(x["nome"] == "Só voz" for x in r["receitas"]) and r["acoes"]
    st, r = _api("POST", "observar", {"pasta": str(tmp_path), "receita": "Só voz"})
    assert st == 200 and r["observando"]["receita"] == "Só voz"
    assert _api("DELETE", "observar", consulta={"pasta": [str(tmp_path)]})[1]["parou"]
    assert _api("DELETE", "receitas/Só voz")[1]["removida"]
    st, r = _api("POST", "observar", {"pasta": str(tmp_path / "x"), "receita": "Só voz"})
    assert st == 400
    st, r = _api("GET", "idiomas")
    assert len(r["idiomas"]) > 90
