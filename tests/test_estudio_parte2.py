"""Estúdio, parte 2: audiolivro, histórias, marca d'água, quem fala, ditado, tela Estúdio."""

import json
import math
import subprocess
import zipfile

import pytest

from optimus.estudio import (
    audio,
    audiolivro,
    diarizar,
    ditado,
    historia,
    marca,
    motores,
    transcrever,
)
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho

np = pytest.importorskip("numpy")
try:
    FFMPEG = audio.ffmpeg()
except ErroEstudio:
    FFMPEG = ""
precisa_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg não instalado")


def _fala_falsa(segundos=1.0, taxa=24000, semente=0):
    """Parecido com voz: nota que varia ao acaso, harmônicos, sopro e sílabas."""
    rng = np.random.default_rng(semente)
    n = int(segundos * taxa)
    t = np.arange(n) / taxa
    passos = rng.normal(0, 1, n // 240 + 2).cumsum()
    f0 = 160 + 50 * np.tanh(np.interp(np.arange(n), np.arange(len(passos)) * 240, passos) / 6)
    fase = 2 * math.pi * np.cumsum(f0) / taxa
    som = sum(np.sin(k * fase) / k for k in range(1, 40))
    sopro = np.convolve(rng.normal(size=n), np.ones(4) / 4, mode="same")
    silabas = 0.5 + 0.5 * np.sin(2 * math.pi * 4 * t + rng.uniform(0, 6))
    return (0.15 * (som + 0.6 * sopro) * silabas).astype("float32")


@pytest.fixture
def voz_falsa(monkeypatch):
    feitos = []

    def falso(texto, perfil, velocidade, config):
        feitos.append((texto, perfil.id))
        return _fala_falsa(0.4 + len(texto) / 40, semente=len(feitos))

    monkeypatch.setattr(motores, "_gerar_padrao", falso)
    return feitos


# ------------------------------------------------------------------ marca d'água
def test_marca_dagua_detecta_so_com_a_chave_certa():
    x = _fala_falsa(6)
    y = marca.marcar(x, 24000)
    assert len(y) == len(x) and y.dtype == np.float32
    ruido = np.sum((y - x) ** 2) / np.sum(x ** 2)
    assert 10 * math.log10(1 / ruido) > 18  # inaudível: bem abaixo da fala
    assert marca.pontuar(y, 24000) >= marca.LIMIAR
    assert marca.pontuar(x, 24000) < marca.LIMIAR
    assert marca.pontuar(y, 24000, "outra") < marca.LIMIAR
    assert marca.pontuar(y * 0.3, 24000) >= marca.LIMIAR  # mudar o volume não apaga
    assert marca.pontuar(_fala_falsa(0.05), 24000) == 0.0  # curto demais: nem tenta


@precisa_ffmpeg
def test_marca_dagua_sobrevive_ao_mp3(tmp_path):
    x = _fala_falsa(6, semente=3)
    marcado = audio.salvar(x, 24000, tmp_path / "ia.mp3")  # salvar já marca
    limpo = audio.salvar(x, 24000, tmp_path / "humano.mp3", marca_ia=False)
    r = marca.detectar(marcado)
    assert r["marcado"] is True and r["pontuacao"] >= marca.LIMIAR
    assert marca.detectar(limpo)["marcado"] is False


# ------------------------------------------------------------------ histórias
ROTEIRO = """# comentário ignorado
Narrador: Era uma noite fria.
Ana: Você ouviu isso?
(pausa 1,5)
[Bruno] Foi só o vento.
E a cidade dormiu.
"""


def test_ler_roteiro_e_elenco():
    falas = historia.ler_roteiro(ROTEIRO)
    assert falas == [("Narrador", "Era uma noite fria."), ("Ana", "Você ouviu isso?"),
                     ("", "1.5"), ("Bruno", "Foi só o vento."),
                     ("Narrador", "E a cidade dormiu.")]
    assert historia.ler_roteiro("Visite http://x.com: agora")[0][0] == "Narrador"
    nomes = historia.personagens(falas)
    elenco = historia.montar_elenco(nomes, {"ana": "Mordomo"})
    assert elenco["Ana"].id == "mordomo"
    assert len({p.id for p in elenco.values()}) == 3  # cada um com uma voz diferente


@precisa_ffmpeg
def test_historia_gera_audio_e_legenda_com_nomes(voz_falsa, tmp_path):
    r = historia.gerar(ROTEIRO, {"Bruno": "Nexus"}, titulo="Noite", saida=tmp_path)
    assert r["falas"] == 4 and r["elenco"]["Bruno"] == "Nexus"
    srt = (tmp_path / "Noite.srt").read_text(encoding="utf-8")
    assert "Ana: Você ouviu isso?" in srt and "Bruno: Foi só o vento." in srt
    assert audio.duracao(r["arquivo"]) > 1.5 + 4 * 0.4
    assert {v for _, v in voz_falsa if v} >= {"nexus"}
    with pytest.raises(ErroEstudio):
        historia.gerar("   \n# nada", saida=tmp_path)


# ------------------------------------------------------------------ audiolivro
def _epub(caminho):
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("META-INF/container.xml",
                   '<container><rootfiles><rootfile full-path="OEBPS/c.opf"/></rootfiles>'
                   "</container>")
        z.writestr("OEBPS/c.opf",
                   '<package><manifest><item id="b" href="b.xhtml"/><item id="a" '
                   'href="a.xhtml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/>'
                   "</spine></package>")
        z.writestr("OEBPS/a.xhtml", "<html><body><h1>Capítulo 1</h1><p>Primeiro &amp; "
                                    "único.</p></body></html>")
        z.writestr("OEBPS/b.xhtml", "<html><body><h1>Capítulo 2</h1><p>Fim.</p></body></html>")


def test_ler_livros_e_dividir_capitulos(tmp_path):
    _epub(tmp_path / "l.epub")
    caps = audiolivro.capitulos(audiolivro.ler_livro(tmp_path / "l.epub"))
    assert caps == [("Capítulo 1", "Primeiro & único."), ("Capítulo 2", "Fim.")]
    with zipfile.ZipFile(tmp_path / "d.docx", "w") as z:
        z.writestr("word/document.xml", "<w:document><w:p><w:t>CAPÍTULO I</w:t></w:p>"
                                        "<w:p><w:t>Texto do docx.</w:t></w:p></w:document>")
    assert audiolivro.capitulos(audiolivro.ler_livro(tmp_path / "d.docx")) == [
        ("CAPÍTULO I", "Texto do docx.")]
    sem_titulos = "\n\n".join(["palavra " * 50] * 5)
    partes = audiolivro.capitulos(sem_titulos, max_palavras=100)
    assert [p[0] for p in partes] == ["Parte 1", "Parte 2", "Parte 3"]
    assert audiolivro.capitulos("Prefácio solto.\n\n# Um\n\nTexto.")[0] == ("Início",
                                                                         "Prefácio solto.")
    with pytest.raises(ErroEstudio):
        audiolivro.ler_livro(tmp_path / "nao-existe.txt")


@precisa_ffmpeg
def test_audiolivro_mp3_por_capitulo_e_m4b_com_capitulos(voz_falsa, tmp_path):
    livro = tmp_path / "O livro d'Ana.md"  # aspas no nome: a lista do ffmpeg precisa escapar
    livro.write_text("# Capítulo 1\n\nOlá.\n\n# Capítulo 2\n\nTchau.", encoding="utf-8")
    r = audiolivro.gerar(livro, autor="Kaik", saida=tmp_path / "saida")
    assert r["capitulos"] == 2 and len(r["arquivos"]) == 2
    # o ffmpeg escreve em UTF-8; no Windows o padrão do Python seria cp1252
    info = subprocess.run([FFMPEG, "-i", r["audiolivro"]], capture_output=True,
                          check=False).stderr.decode("utf-8", "replace")
    assert "Chapter #0:1" in info and "Capítulo 2" in info and "Kaik" in info
    chamadas = len(voz_falsa)
    audiolivro.gerar(livro, saida=tmp_path / "saida", m4b=False)  # retoma do cache
    assert len(voz_falsa) == chamadas


# ------------------------------------------------------------------ quem fala
def test_atribuir_falantes_por_sobreposicao():
    turnos = [Trecho(0, 5, "", "Pessoa 1"), Trecho(5, 10, "", "Pessoa 2")]
    falas = [Trecho(0.5, 4, "oi"), Trecho(4.5, 9, "tudo bem"), Trecho(20, 21, "longe")]
    r = diarizar.atribuir(falas, turnos)
    assert [t.falante for t in r] == ["Pessoa 1", "Pessoa 2", "Pessoa 2"]
    assert diarizar.atribuir(falas, [])[0].falante == ""


def test_transcricao_sem_motor_explica_o_que_instalar(monkeypatch, tmp_path):
    arquivo = tmp_path / "a.wav"
    arquivo.write_bytes(audio.wav_bytes(_fala_falsa(0.5), 16000))
    monkeypatch.setattr(transcrever, "motor_disponivel", lambda: "")
    with pytest.raises(ErroEstudio, match="pip install"):
        transcrever.transcrever(arquivo)


# ------------------------------------------------------------------ ditado
def test_ditado_pontuacao_falada_e_maiusculas():
    p = ditado.processar
    assert p("olá tudo bem vírgula como vai ponto de interrogação nova linha eu vou bem "
             "ponto final") == "Olá tudo bem, como vai?\nEu vou bem."
    assert p("e você", "Oi.") == " E você"
    assert p("meu nome é kaik", "Oi, ") == "meu nome é kaik"
    assert p("ele disse abre aspas sim fecha aspas ponto final") == "Ele disse “sim”."
    assert p("vírgula e depois", "Oi") == ", e depois"
    assert p("") == ""


def test_ditado_escuta_transcreve_e_digita(monkeypatch):
    from optimus.voice import stt

    gravacoes = iter([_fala_falsa(1), None, _fala_falsa(1)])
    digitados, estados = [], []
    falas = iter(["oi ponto final", "tudo certo"])

    def gravar(**_):
        try:
            return next(gravacoes)
        except StopIteration:
            d.ligado = False
            return None

    monkeypatch.setattr(stt, "gravar_ate_silencio", gravar)
    monkeypatch.setattr(ditado, "_transcrever", lambda a, i, c: next(falas))
    monkeypatch.setattr(ditado, "digitar", lambda t: digitados.append(t) or True)
    d = ditado.Ditado(ao_mudar=lambda e, t="": estados.append(e))
    d.iniciar()
    d._linha.join(5)
    assert digitados == ["Oi.", " Tudo certo"]
    assert "ouvindo" in estados and "digitado" in estados


def test_ditado_avisa_sem_microfone(monkeypatch):
    from optimus.voice import stt

    def sem_mic(**_):
        raise OSError("nenhum microfone")

    monkeypatch.setattr(stt, "gravar_ate_silencio", sem_mic)
    avisos = []
    d = ditado.Ditado(ao_mudar=lambda e, t="": avisos.append((e, t)))
    d.iniciar()
    d._linha.join(5)
    assert not d.ligado and avisos[-1][0] == "erro" and "microfone" in avisos[-1][1]


# ------------------------------------------------------------------ ferramentas e rotas
def test_pares_de_elenco():
    from optimus.tools.estudio import _pares

    assert _pares("Pessoa 1=Nexus; Pessoa 2: Aurora,Ana = Valkyrie") == {
        "Pessoa 1": "Nexus", "Pessoa 2": "Aurora", "Ana": "Valkyrie"}
    assert _pares("") == {} and _pares("sem igual") == {}


@pytest.mark.parametrize("frase, esperada", [
    ("transforma o livro.epub em audiolivro", "estudio_audiolivro"),
    ("faz um podcast com dois personagens", "estudio_historia"),
    ("separa a voz da música desse vídeo", "estudio_separar_voz"),
    ("quem fala nesse áudio?", "estudio_quem_fala"),
    ("esse áudio tem marca d'água de IA?", "estudio_verificar_ia"),
    ("narra esse texto com a voz mordomo", "estudio_falar"),
])
def test_roteador_acha_as_ferramentas_novas(frase, esperada):
    import optimus.tools  # noqa: F401 - registra as ferramentas
    from optimus.roteador import selecionar_ferramentas
    from optimus.tools.base import registradas

    assert esperada in selecionar_ferramentas(frase, registradas(), pequeno=True)


# ------------------------------------------------------------------ tela Estúdio (API)
class _OptimusFalso:
    def __init__(self):
        from optimus import config as cfg

        self.config = cfg.carregar()
        self.motor = None
        self.banco = None

    def modelo_atual(self):
        return "teste"


def _api(metodo, caminho, corpo=b"", tipo="application/json", consulta=None):
    from optimus.web import estudio_api

    if isinstance(corpo, dict):
        corpo = json.dumps(corpo).encode()
    return estudio_api.atender(metodo, caminho.split("/"), consulta or {}, tipo, corpo,
                               _OptimusFalso())


@precisa_ffmpeg
def test_api_estudio_falar_e_servir_so_arquivos_do_estudio(voz_falsa, tmp_path):
    st, r = _api("GET", "vozes")
    assert st == 200 and any(v["nome"] == "Mordomo" for v in r["vozes"]) and r["declaracao"]
    st, r = _api("POST", "falar", {"texto": "Olá", "voz": "Mordomo",
                                   "arquivo": str(tmp_path / "fora.mp3")})
    assert st == 200 and not (tmp_path / "fora.mp3").exists()  # a tela não escolhe o destino
    st, arquivo = _api("GET", "arquivo", consulta={"caminho": [r["arquivo"]]})
    assert st == 200 and arquivo.name.endswith(".mp3")
    segredo = tmp_path / "segredo.txt"
    segredo.write_text("x")
    for caminho in (str(segredo), "/etc/passwd", r["arquivo"] + "/../../../../etc/passwd"):
        assert _api("GET", "arquivo", consulta={"caminho": [caminho]})[0] == 404
    st, r = _api("GET", "historico")
    assert st == 200 and r["itens"][0]["tipo"] == "narracao"


def test_api_estudio_envio_clonagem_pronuncia_e_erros():
    limite = "LIMITE"
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; "
             f"filename=\"../../meu video.mp4\"\r\nContent-Type: video/mp4\r\n\r\n").encode() \
        + b"dados" + f"\r\n--{limite}--\r\n".encode()
    st, r = _api("POST", "enviar", corpo, f"multipart/form-data; boundary={limite}")
    assert st == 200 and r["caminho"].endswith("meu video.mp4") and "/entradas/" in \
        r["caminho"].replace("\\", "/")
    st, r = _api("POST", "clonar", {"nome": "X", "arquivo": "a.wav"})
    assert st == 400 and "autorização" in r["erro"]
    st, r = _api("POST", "dublar", {"arquivo": "a.mp4", "voz_original": "true"})
    assert st == 400
    st, r = _api("POST", "pronuncia", {"escrito": "Kaik", "falado": "Káique"})
    assert st == 200 and r["regras"][0]["falado"] == "Káique"
    assert _api("DELETE", "pronuncia/Kaik")[1]["removido"] is True
    assert _api("POST", "falar", {})[0] == 400  # faltou o texto
    assert _api("GET", "nada")[0] == 404
    assert _api("POST", "falar", b"{quebrado")[0] == 400
    st, r = _api("GET", "idiomas")
    assert any(i["codigo"] == "pt-BR" for i in r["idiomas"])


@precisa_ffmpeg
def test_api_estudio_historia_vai_para_a_fila(voz_falsa):
    from optimus.estudio import fila

    fila.reiniciar()
    st, r = _api("POST", "historia", {"roteiro": "Ana: Oi.\nBruno: Olá.", "titulo": "Teste"})
    assert st == 200 and r["tarefa"]
    feita = fila.fila().esperar(r["tarefa"], 60)
    assert feita.estado == "concluida", feita.erro
    st, r = _api("GET", "tarefas")
    assert r["tarefas"][-1]["resultado"]["arquivo"].endswith("Teste.mp3")


# ------------------------------------------------------------------ achados do review
def test_pacote_de_modelo_nao_escreve_fora_da_pasta(tmp_path):
    import io
    import tarfile

    pacote = tmp_path / "m.tar.bz2"
    with tarfile.open(pacote, "w:bz2") as tar:
        info = tarfile.TarInfo("../modelos-extra/f.txt")  # mesmo prefixo, outra pasta
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    (tmp_path / "modelos").mkdir()
    with pytest.raises(ErroEstudio):
        transcrever._extrair(pacote, tmp_path / "modelos")
    assert not (tmp_path / "modelos-extra").exists()


@precisa_ffmpeg
def test_titulo_do_audiolivro_nao_sai_da_pasta(voz_falsa, tmp_path):
    livro = tmp_path / "l.txt"
    livro.write_text("Uma frase só.", encoding="utf-8")
    r = audiolivro.gerar(livro, titulo="../../fora", saida=tmp_path / "saida", m4b=False)
    assert (tmp_path / "saida") in __import__("pathlib").Path(r["pasta"]).parents
    assert r["titulo"] == "../../fora"


def test_envio_grande_vai_em_pedacos_para_o_disco():
    import io

    from optimus.web import estudio_api

    dados = b"v" * (3 * 1024 * 1024 + 5)
    salvo = estudio_api.receber_envio("../vídeo grande.mp4", io.BytesIO(dados), len(dados))
    assert salvo.read_bytes() == dados and salvo.parent.name == "entradas"
    with pytest.raises(ErroEstudio):
        estudio_api.receber_envio("x.mp4", io.BytesIO(b"curto"), 100)
