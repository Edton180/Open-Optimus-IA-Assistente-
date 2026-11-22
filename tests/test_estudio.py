"""Estúdio de voz: legendas, idiomas, pronúncia, vozes, tradução, fila, dublagem e API."""

import json
import math
import subprocess
import zipfile

import pytest

from optimus.estudio import (
    audio,
    dublagem,
    fila,
    idiomas,
    legendas,
    motores,
    pronuncia,
    traduzir,
    transcrever,
    vozes,
)
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho

np = pytest.importorskip("numpy")
try:
    FFMPEG = audio.ffmpeg()
except ErroEstudio:
    FFMPEG = ""
TEM_FFMPEG = bool(FFMPEG)
precisa_ffmpeg = pytest.mark.skipif(not TEM_FFMPEG, reason="ffmpeg não instalado")


def _seno(segundos=1.0, taxa=24000, freq=220.0):
    t = np.arange(int(segundos * taxa), dtype="float32") / taxa
    return (0.5 * np.sin(2 * math.pi * freq * t)).astype("float32")


# ------------------------------------------------------------------ legendas
SRT = """1
00:00:01,000 --> 00:00:03,500
<i>Olá</i>, mundo!

2
00:00:04,000 --> 00:00:06,000
Ana: Tudo bem?
"""


def test_srt_ida_e_volta():
    t = legendas.ler(SRT)
    assert [x.texto for x in t] == ["Olá, mundo!", "Tudo bem?"]
    assert t[0].inicio == 1.0 and t[0].fim == 3.5 and t[1].falante == "Ana"
    de_novo = legendas.ler(legendas.para_srt(t, com_falante=True))
    assert de_novo[1].falante == "Ana" and de_novo[0].texto == "Olá, mundo!"
    vtt = legendas.para_vtt(t)
    assert vtt.startswith("WEBVTT") and "00:00:01.000 --> 00:00:03.500" in vtt
    assert [x.texto for x in legendas.ler(vtt)] == ["Olá, mundo!", "Tudo bem?"]


def test_quebra_e_divisao():
    longa = "Esta é uma legenda bastante comprida que precisa ser quebrada em duas linhas"
    linhas = legendas.quebrar_linhas(longa).split("\n")
    assert len(linhas) == 2 and all(len(x) <= 42 for x in linhas)
    partes = legendas.dividir_longos([Trecho(0, 10, "Primeira frase longa aqui. " * 6)])
    assert len(partes) > 1 and partes[-1].fim == pytest.approx(10, abs=0.01)
    assert all(len(p.texto) <= 84 for p in partes)
    assert legendas.deslocar([Trecho(1, 2, "a")], -1.5)[0].inicio == 0.0


# ------------------------------------------------------------------ idiomas
def test_idiomas_pt_br_padrao():
    assert idiomas.idioma("").codigo == "pt-BR"
    assert idiomas.idioma("português").codigo == "pt-BR"
    assert idiomas.idioma("para inglês").codigo == "en-US"
    assert idiomas.idioma("es-mx").codigo == "es-MX"
    assert idiomas.do_whisper("pt").codigo == "pt-BR"
    assert "Brasil" in idiomas.idioma("pt-BR").instrucao
    with pytest.raises(ValueError):
        idiomas.idioma("klingon")


# ------------------------------------------------------------------ pronúncia
def test_pronuncia(tmp_path):
    pronuncia.adicionar("Kaik", "Káique")
    pronuncia.adicionar("SQL", "ésse quê éle")
    assert pronuncia.aplicar("Oi kaik, sabe SQL? Kaikito não.") == \
        "Oi Káique, sabe ésse quê éle? Kaikito não."
    arq = tmp_path / "regras.txt"
    arq.write_text("# comentário\nGPU = gê pê u\n", encoding="utf-8")
    assert pronuncia.importar(arq) == 1
    assert pronuncia.remover("SQL") and len(pronuncia.listar()) == 2


# ------------------------------------------------------------------ vozes
def test_vozes_prontas_e_mordomo():
    nomes = [p.nome for p in vozes.listar()]
    assert "Mordomo" in nomes and "Valkyrie" in nomes
    assert vozes.obter("").id == "valkyrie"
    assert vozes.obter("valquíria").id == "valkyrie"
    with pytest.raises(ErroEstudio):
        vozes.obter("ninguém")


def test_descricao_vira_parametros():
    a = vozes.interpretar_descricao("Voz masculina, grave e calma")
    assert a["genero"] == "masculina" and a["tom"] < 0 and a["velocidade"] < 1
    b = vozes.interpretar_descricao("mulher jovem e animada")
    assert b["genero"] == "feminina" and b["tom"] > 0 and b["velocidade"] > 1
    assert vozes.interpretar_descricao("robótica")["efeito"] == "cyber"
    p = vozes.criar("Narrador", "homem idoso, grave")
    assert p.tipo == "criada" and p.base == "prime" and p.tom <= -3
    assert vozes.obter("narrador").id == p.id
    vozes.editar("Narrador", tom=1.0)
    assert vozes.obter("Narrador").tom == 1.0
    assert vozes.apagar("Narrador").id == p.id
    with pytest.raises(ErroEstudio):
        vozes.apagar("Prime")


def test_clonar_exige_consentimento(tmp_path):
    with pytest.raises(ErroEstudio, match="consentimento"):
        vozes.clonar("Eu", tmp_path / "x.wav", consentimento=False)


@precisa_ffmpeg
def test_clonar_exportar_importar(tmp_path):
    amostra = tmp_path / "eu.wav"
    amostra.write_bytes(audio.wav_bytes(_seno(8), 24000))
    p = vozes.clonar("Minha voz", amostra, True, genero="masculina")
    assert p.tipo == "clonada" and p.motor == "clone" and p.caminho_amostra().exists()
    assert "autorização" in p.consentimento["declaracao"]
    pacote = vozes.exportar("Minha voz", tmp_path / "minha")
    assert pacote.suffix == ".optimusvoz"
    copia = vozes.importar(pacote)
    assert copia.id != p.id and copia.caminho_amostra().exists()
    curta = tmp_path / "curta.wav"
    curta.write_bytes(audio.wav_bytes(_seno(2), 24000))
    with pytest.raises(ErroEstudio, match="pelo menos"):
        vozes.clonar("Curta", curta, True)


def test_importar_recusa_pacote_estranho(tmp_path):
    ruim = tmp_path / "ruim.optimusvoz"
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr("perfil.json", json.dumps({"id": "x", "nome": "X", "tipo": "clonada"}))
        z.writestr("../fora.txt", "x")
    with pytest.raises(ErroEstudio):
        vozes.importar(ruim)


# ------------------------------------------------------------------ tradução
def _llm_eco(prefixo="PT:", pular=()):
    chamadas = []

    def llm(mensagens):
        chamadas.append(mensagens)
        saida = []
        for linha in mensagens[-1]["content"].splitlines():
            n, texto = linha.split("] ", 1)
            if int(n[1:]) in pular and len(chamadas) == 1:
                continue
            saida.append(f"{n}] {prefixo} {texto}")
        return "\n".join(saida)

    llm.chamadas = chamadas
    return llm


def test_traduz_mantendo_tempos_e_glossario():
    traduzir.salvar_glossario("canal", ["Optimus"], {"deploy": "implantação"})
    llm = _llm_eco()
    trechos = [Trecho(0, 1, "Optimus is here"), Trecho(1, 2, "Let's deploy")]
    novos = traduzir.traduzir(trechos, "pt-BR", llm, "en", projeto="canal")
    assert [t.inicio for t in novos] == [0, 1]
    assert novos[0].texto == "PT: Optimus is here"
    sistema = llm.chamadas[0][0]["content"]
    assert "português do Brasil" in sistema and "deploy → implantação" in sistema
    assert "⟦0⟧" in llm.chamadas[0][1]["content"]  # o termo foi protegido


def test_traducao_refaz_linha_que_faltou_e_nunca_perde():
    llm = _llm_eco(pular=(2,))
    textos = traduzir.traduzir_textos(["a", "b", "c"], "en", llm)
    assert textos == ["PT: a", "PT: b", "PT: c"] and len(llm.chamadas) == 2
    assert traduzir.traduzir_textos(["fica"], "en", lambda m: "") == ["fica"]


def test_extrair_termos():
    termos = traduzir.extrair_termos("texto", lambda m: 'ok {"termos": ["Kaik", "Optimus"]}')
    assert termos == ["Kaik", "Optimus"]


# ------------------------------------------------------------------ fila
def test_fila_roda_progresso_e_falha(tmp_path):
    fila.reiniciar()
    f = fila.fila()

    def bom(progresso, cancelado, x=0):
        progresso(0.5, "meio")
        return {"dobro": x * 2}

    def ruim(progresso, cancelado):
        raise ErroEstudio("deu ruim")

    t1 = f.adicionar("teste", "bom", bom, x=21)
    t2 = f.adicionar("teste", "ruim", ruim)
    assert f.esperar(t1.id, 5).resultado == {"dobro": 42}
    assert f.esperar(t2.id, 5).estado == "falhou" and "deu ruim" in t2.erro
    fila.reiniciar()
    assert {t.id for t in fila.fila().listar()} >= {t1.id, t2.id}  # ficou registrado


def test_fila_cancela():
    fila.reiniciar()
    f = fila.fila()
    import time

    def longo(progresso, cancelado):
        while not cancelado():
            time.sleep(0.01)
        return {}

    t = f.adicionar("teste", "longo", longo)
    time.sleep(0.05)
    assert f.cancelar(t.id)
    assert f.esperar(t.id, 5).estado == "cancelada"


# ------------------------------------------------------------------ geração
def test_dividir_texto():
    partes = motores.dividir_texto("Frase um. " * 80, maximo=100)
    assert all(len(p) <= 100 for p in partes) and len(partes) > 5
    sem_ponto = motores.dividir_texto("palavra " * 100, maximo=120)
    assert all(len(p) <= 121 for p in sem_ponto)


@pytest.fixture
def voz_falsa(monkeypatch):
    feitos = []

    def falso(texto, perfil, velocidade, config):
        feitos.append(texto)
        return _seno(0.4 + len(texto) / 40)

    monkeypatch.setattr(motores, "_gerar_padrao", falso)
    return feitos


def test_gerar_usa_pronuncia_e_frases(voz_falsa):
    pronuncia.adicionar("Kaik", "Káique")
    x = motores.gerar("Oi Kaik. Tudo certo?", "Prime")
    assert voz_falsa == ["Oi Káique.", "Tudo certo?"] or voz_falsa == ["Oi Káique. Tudo certo?"]
    assert x.dtype == np.float32 and np.max(np.abs(x)) <= 0.91


def test_clone_sem_motor_explica_como_instalar(monkeypatch, tmp_path):
    monkeypatch.setattr(motores, "clonagem_instalada", lambda: False)
    p = vozes.Perfil("x", "X", "clonada", "clone", amostra="amostra.wav")
    (vozes.pasta_vozes() / "x").mkdir(parents=True)
    (vozes.pasta_vozes() / "x" / "amostra.wav").write_bytes(b"")
    with pytest.raises(ErroEstudio, match="chatterbox"):
        motores.gerar("oi", p)


def test_clone_chama_chatterbox_em_portugues(monkeypatch):
    chamadas = {}

    class Falso:
        sr = 24000

        def generate(self, texto, **k):
            chamadas.update(k, texto=texto)
            return _seno(0.5)

    monkeypatch.setattr(motores, "_modelo_clone", lambda: Falso())
    p = vozes.Perfil("x", "X", "clonada", "clone", amostra="amostra.wav", expressividade=0.9)
    (vozes.pasta_vozes() / "x").mkdir(parents=True)
    (vozes.pasta_vozes() / "x" / "amostra.wav").write_bytes(b"RIFF")
    motores.gerar("Bom dia!", p, "pt-BR")
    assert chamadas["language_id"] == "pt" and chamadas["exaggeration"] == 0.9
    assert chamadas["audio_prompt_path"].endswith("amostra.wav")


@precisa_ffmpeg
def test_tom_e_ritmo_com_ffmpeg():
    x = _seno(1.0)
    assert abs(len(motores.mudar_tom(x, 24000, -3)) - len(x)) < 2400  # mesma duração
    assert len(audio.esticar(x, 24000, 2.0)) < len(x) * 0.6
    y, fator = audio.caber(_seno(3.0), 24000, 2.5)
    assert fator == pytest.approx(1.2, abs=0.01) and len(y) / 24000 < 2.6


@precisa_ffmpeg
def test_salvar_mp3_com_etiqueta_de_ia(tmp_path):
    arq = audio.salvar(_seno(1), 24000, tmp_path / "a.mp3")
    info = subprocess.run([FFMPEG, "-hide_banner", "-i", str(arq)], capture_output=True,
                          text=True).stderr
    assert "Voz gerada por IA" in info
    assert len(audio.carregar(arq, 16000)) == pytest.approx(16000, rel=0.1)


# ------------------------------------------------------------------ dublagem de ponta a ponta
@precisa_ffmpeg
def test_dublar_e_legendar_video(tmp_path, monkeypatch, voz_falsa):
    video = tmp_path / "aula.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=160x120:rate=10", "-f", "lavfi", "-i",
                    "sine=frequency=300:duration=4", "-t", "4", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
    monkeypatch.setattr(transcrever, "transcrever", lambda *a, **k: (
        [Trecho(0.2, 1.5, "Hello there."), Trecho(2.0, 3.5, "Welcome to class.")],
        idiomas.idioma("en-US")))
    progresso = []
    r = dublagem.dublar(video, "pt-BR", "Prime", llm=_llm_eco("Olá"), saida=tmp_path / "out",
                        progresso=lambda v, m="": progresso.append(v))
    assert (tmp_path / "out" / "aula.dublado.pt-BR.mp4").exists()
    assert r["trechos"] == 2 and r["voz"] == "Prime" and progresso[-1] >= 0.9
    srt = legendas.ler_arquivo(r["legenda"])
    assert srt[0].texto.startswith("Olá") and srt[1].inicio == 2.0
    faixas = subprocess.run([FFMPEG, "-hide_banner", "-i", r["video"]], capture_output=True,
                            text=True).stderr
    assert "Subtitle" in faixas and "Audio" in faixas
    # Recomeça de onde parou: nada é gerado de novo.
    antes = len(voz_falsa)
    dublagem.dublar(video, "pt-BR", "Prime", llm=_llm_eco("Olá"), saida=tmp_path / "out")
    assert len(voz_falsa) == antes
    leg = dublagem.legendar(video, "", queimar=True, saida=tmp_path / "out")
    assert leg["idioma_legenda"] == "inglês" and leg["video"].endswith(".mp4")


def test_dublar_com_voz_original_exige_consentimento(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(audio, "duracao", lambda c: 4.0)
    monkeypatch.setattr(transcrever, "transcrever", lambda *a, **k: (
        [Trecho(0, 3, "oi")], idiomas.idioma("pt-BR")))
    with pytest.raises(ErroEstudio, match="autorização"):
        dublagem.dublar(video, "en-US", voz_original=True, consentimento=False,
                        llm=_llm_eco())


def test_amostra_da_fala_pega_os_trechos_longos():
    som = _seno(30)
    trechos = [Trecho(0, 1, "a"), Trecho(2, 8, "b"), Trecho(10, 19, "c"), Trecho(20, 21, "d")]
    x = dublagem.amostra_da_fala(trechos, som, 24000)
    assert len(x) == pytest.approx(15 * 24000, rel=0.01)
    with pytest.raises(ErroEstudio):
        dublagem.amostra_da_fala([Trecho(0, 2, "x")], som, 24000)


# ------------------------------------------------------------------ API compatível com OpenAI
def test_api_openai_fala_e_modelos(voz_falsa):
    from optimus.web import openai_audio

    st, tipo, dados = openai_audio.atender("GET", "/v1/models", "", b"", None)
    assert st == 200 and "optimus-tts" in dados.decode()
    corpo = json.dumps({"input": "Olá!", "voice": "onyx", "response_format": "pcm"}).encode()
    st, tipo, dados = openai_audio.atender("POST", "/v1/audio/speech", "application/json",
                                           corpo, None)
    assert st == 200 and tipo == "audio/L16" and len(dados) > 1000
    st, _, dados = openai_audio.atender("POST", "/v1/audio/speech", "", b"{}", None)
    assert st == 400


def test_api_openai_transcricao_multipart(monkeypatch):
    from optimus.web import openai_audio

    monkeypatch.setattr(transcrever, "transcrever", lambda *a, **k: (
        [Trecho(0, 1, "bom dia")], idiomas.idioma("pt-BR")))
    limite = "XyZ"
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; "
             f"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\nRIFF....\r\n"
             f"--{limite}\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\n"
             f"srt\r\n--{limite}--\r\n").encode()
    st, _tipo, dados = openai_audio.atender(
        "POST", "/v1/audio/transcriptions", f"multipart/form-data; boundary={limite}", corpo,
        None)
    assert st == 200 and "bom dia" in dados.decode() and "-->" in dados.decode()


# ------------------------------------------------------------------ ferramentas e roteador
def test_roteador_estudio():
    from optimus.roteador import selecionar_ferramentas
    from optimus.tools.base import registradas

    todas = registradas()
    casos = {
        "dubla esse vídeo para português com a minha voz": "estudio_dublar",
        "legenda o video.mp4 em inglês": "estudio_legendar",
        "transcreve a reunião.mp3": "estudio_transcrever",
        "clona minha voz com o arquivo voz.m4a": "estudio_clonar_voz",
        "narra esse texto com a voz Mordomo": "estudio_falar",
        "cria uma voz feminina jovem": "estudio_criar_voz",
        "como está a dublagem?": "estudio_tarefas",
    }
    for pedido, nome in casos.items():
        assert nome in selecionar_ferramentas(pedido, todas), pedido
    assert not selecionar_ferramentas("oi, tudo bem?", todas)


def test_ferramenta_clonar_sempre_pede_confirmacao():
    from optimus.safety import CRITICO
    from optimus.tools.base import registradas

    av = registradas()["estudio_clonar_voz"].avaliar({"arquivo": "a.wav"}, None)
    assert av.nivel == CRITICO and "autorização" in av.motivo


def test_ferramenta_falar_gera_arquivo(tmp_path, voz_falsa, monkeypatch):
    from optimus.tools import estudio
    from optimus.tools.base import Contexto

    monkeypatch.setattr(audio, "salvar", lambda x, taxa, destino, **k: destino)
    r = estudio.estudio_falar(Contexto(config=None, pasta_trabalho=tmp_path), "Olá",
                              voz="Prime")
    assert r["voz"] == "Prime" and r["arquivo"].endswith(".mp3")
