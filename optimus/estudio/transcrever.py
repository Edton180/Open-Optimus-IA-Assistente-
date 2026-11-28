"""Transcrição de arquivos de áudio e vídeo (offline) para TXT, SRT e VTT.

Dois motores, escolhidos sozinhos:
- **faster-whisper** (`pip install faster-whisper`): o mais preciso; baixa o modelo do
  Hugging Face na primeira vez.
- **sherpa-onnx** (`pip install sherpa-onnx`): Whisper em ONNX com detecção de fala (Silero
  VAD); baixa os modelos do GitHub. Serve de reserva quando o Hugging Face não abre.

- **remoto**: um servidor compatível com a OpenAI (`estudio.servidor_voz_url`), para usar a
  placa de vídeo de outra máquina.

Detecta o idioma sozinho, ou use `idioma="pt-BR"`. Para o melhor resultado em português do
Brasil, use "large-v3-turbo" (com placa de vídeo) ou "medium"/"small" no CPU.
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

from optimus.estudio import audio, idiomas, pasta_estudio
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho
from optimus.voice.stt import limpar_transcricao

_MODELOS: dict[str, object] = {}
_BASE_SHERPA = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
# nome do faster-whisper → pacote do sherpa-onnx
_SHERPA = {"tiny": "tiny", "base": "base", "small": "small", "medium": "medium",
           "large-v3-turbo": "turbo", "turbo": "turbo", "large-v3": "large-v3"}


def _tem(modulo: str) -> bool:
    try:
        from optimus.pacotes import modulo_instalado

        return modulo_instalado(modulo)
    except (ImportError, ValueError):
        return False


def motor_disponivel() -> str:
    if _tem("faster_whisper"):
        return "faster-whisper"
    if _tem("sherpa_onnx"):
        return "sherpa-onnx"
    return ""


def modelo_padrao(config=None) -> str:
    if config is not None:
        escolhido = config.get("estudio", "modelo_transcricao", "")
        if escolhido:
            return escolhido
        if str(config.get("estudio", "desempenho", "auto")).strip().lower() != "auto":
            from optimus.estudio import desempenho

            return desempenho.atual(config).transcricao
    return "large-v3-turbo" if shutil.which("nvidia-smi") else "small"


# ---------------------------------------------------------------------- faster-whisper
def _faster(caminho: Path, codigo: str | None, modelo: str, progresso, cancelado):
    if modelo not in _MODELOS:
        from optimus.voice.stt import Ouvinte

        _MODELOS[modelo] = Ouvinte(modelo)._carregar()
    whisper = _MODELOS[modelo]
    segmentos, info = whisper.transcribe(str(caminho), language=codigo, vad_filter=True,
                                         beam_size=5, condition_on_previous_text=False)
    total = float(getattr(info, "duration", 0) or 0)
    trechos: list[Trecho] = []
    for s in segmentos:
        if cancelado and cancelado():
            raise ErroEstudio("Cancelado.")
        texto = limpar_transcricao(s.text)
        if texto:
            trechos.append(Trecho(round(float(s.start), 3), round(float(s.end), 3), texto))
        if progresso and total:
            progresso(min(1.0, float(s.end) / total),
                      f"Transcrevendo… {int(s.end)}s de {int(total)}s")
    return trechos, getattr(info, "language", "") or ""


# ---------------------------------------------------------------------- sherpa-onnx
def _baixar(url: str, destino: Path, progresso=None, mensagem: str = "") -> Path:
    import httpx

    destino.parent.mkdir(parents=True, exist_ok=True)
    if progresso and mensagem:
        progresso(0.0, mensagem)
    parcial = destino.with_name(destino.name + ".parcial")
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        with open(parcial, "wb") as f:
            f.writelines(r.iter_bytes())
    parcial.replace(destino)
    return destino


def _extrair(pacote: Path, pasta: Path) -> None:
    with tarfile.open(pacote) as tar:
        raiz = pasta.resolve()
        for membro in tar.getmembers():
            alvo = (pasta / membro.name).resolve()
            if not alvo.is_relative_to(raiz) or membro.issym() or membro.islnk():
                raise ErroEstudio("Pacote de modelo inválido.")
        tar.extractall(pasta)  # conferido acima


def _modelo_sherpa(nome: str, progresso=None) -> tuple[Path, Path]:
    """Baixa (uma vez) o Whisper ONNX e o detector de fala. Devolve (pasta, vad)."""
    pacote_nome = f"sherpa-onnx-whisper-{_SHERPA.get(nome, 'small')}"
    raiz = pasta_estudio() / "modelos" / "transcricao"
    pasta = raiz / pacote_nome
    if not (pasta / "tokens.txt").exists() and not any(pasta.glob("*-tokens.txt")):
        pacote = _baixar(_BASE_SHERPA + pacote_nome + ".tar.bz2", raiz / "modelo.tar.bz2",
                         progresso, "Baixando o modelo de transcrição (só na primeira vez)…")
        _extrair(pacote, raiz)
        pacote.unlink(missing_ok=True)
    vad = raiz / "silero_vad.onnx"
    if not vad.exists():
        _baixar(_BASE_SHERPA + "silero_vad.onnx", vad)
    return pasta, vad


def _arquivo(pasta: Path, padrao: str) -> str:
    """Primeiro arquivo que casa com o padrão, preferindo a versão int8 (mais leve)."""
    achados = sorted(pasta.glob(padrao), key=lambda p: ("int8" not in p.name, p.name))
    if not achados:
        raise ErroEstudio(f"Modelo incompleto em {pasta} (falta {padrao}).")
    return str(achados[0])


def _sherpa(caminho: Path, codigo: str | None, modelo: str, progresso, cancelado):
    import os

    import sherpa_onnx

    pasta, vad_arq = _modelo_sherpa(modelo, progresso)
    chave = f"sherpa:{pasta.name}:{codigo or ''}"
    if chave not in _MODELOS:
        _MODELOS[chave] = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=_arquivo(pasta, "*encoder*.onnx"), decoder=_arquivo(pasta, "*decoder*.onnx"),
            tokens=_arquivo(pasta, "*tokens.txt"), language=codigo or "",
            task="transcribe", num_threads=max(1, min(8, (os.cpu_count() or 2) - 1)))
    reconhecedor = _MODELOS[chave]
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(vad_arq)
    config.silero_vad.min_silence_duration = 0.35
    config.silero_vad.max_speech_duration = 20
    config.sample_rate = 16000
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=120)
    amostras = audio.carregar(caminho, 16000)
    total = len(amostras) / 16000 or 1
    trechos: list[Trecho] = []
    lingua = ""

    def esvaziar():
        nonlocal lingua
        while not vad.empty():
            if cancelado and cancelado():
                raise ErroEstudio("Cancelado.")
            seg = vad.front
            fluxo = reconhecedor.create_stream()
            fluxo.accept_waveform(16000, seg.samples)
            reconhecedor.decode_stream(fluxo)
            texto = limpar_transcricao(fluxo.result.text)
            lingua = lingua or str(getattr(fluxo.result, "lang", "") or "").strip("<|>")
            inicio = seg.start / 16000
            if texto:
                trechos.append(Trecho(round(inicio, 3),
                                      round(inicio + len(seg.samples) / 16000, 3), texto))
            if progresso:
                progresso(min(1.0, inicio / total), f"Transcrevendo… {int(inicio)}s de "
                                                    f"{int(total)}s")
            vad.pop()

    janela = config.silero_vad.window_size
    for i in range(0, len(amostras), janela):
        vad.accept_waveform(amostras[i:i + janela])
        esvaziar()
    vad.flush()
    esvaziar()
    return trechos, lingua


# ---------------------------------------------------------------------- API pública
def transcrever(caminho: str | Path, idioma: str = "", modelo: str = "", config=None,
                progresso=None, cancelado=None, motor: str = "") -> tuple[list[Trecho],
                                                                         idiomas.Idioma]:
    """Devolve (trechos com tempo, idioma falado)."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroEstudio(f"Arquivo não encontrado: {caminho}")
    codigo = (idiomas.idioma(idioma).whisper or None) if idioma else None
    nome = modelo or modelo_padrao(config)
    escolhido = motor or (config.get("estudio", "motor_transcricao", "") if config else "") \
        or motor_disponivel()
    if not escolhido:
        from optimus.estudio import remoto

        if remoto.configurado(config):
            escolhido = "remoto"
    if not escolhido:
        raise ErroEstudio("A transcrição precisa de um motor: pip install faster-whisper "
                          "(ou pip install sherpa-onnx)")
    if escolhido == "remoto":
        from optimus.estudio import remoto

        (progresso or (lambda *a: None))(0.05, "Enviando para o servidor de transcrição…")
        trechos, lingua = remoto.transcrever(caminho, idioma, config)
        detectado = lingua
        lingua = idiomas.codigo_detectado(detectado)  # "portuguese" (OpenAI) ou "pt"
        if not lingua and not idioma:
            raise ErroEstudio(f"Não reconheci o idioma '{detectado}' que o servidor devolveu. "
                              "Diga o idioma do áudio (ex.: idioma=pt-BR).")
    elif escolhido == "faster-whisper":
        try:
            trechos, lingua = _faster(caminho, codigo, nome, progresso, cancelado)
        except ErroEstudio:
            raise
        except Exception as erro:  # sem acesso ao Hugging Face, por exemplo
            if not _tem("sherpa_onnx"):
                raise ErroEstudio(f"Não consegui transcrever: {erro}") from erro
            trechos, lingua = _sherpa(caminho, codigo, nome, progresso, cancelado)
    else:
        trechos, lingua = _sherpa(caminho, codigo, nome, progresso, cancelado)
    falado = idiomas.idioma(idioma) if idioma else idiomas.do_whisper(lingua or "pt")
    return trechos, falado


def descarregar() -> None:
    _MODELOS.clear()
