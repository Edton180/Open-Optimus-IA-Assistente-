"""Transcrição de arquivos de áudio e vídeo (faster-whisper, offline) para TXT, SRT e VTT.

Detecta o idioma sozinho, ou use `idioma="pt-BR"`. Para o melhor resultado em português do
Brasil, use o modelo "large-v3-turbo" (com placa de vídeo) ou "medium"/"small" no CPU.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from optimus.estudio import idiomas
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho
from optimus.voice.stt import limpar_transcricao

_MODELOS: dict[str, object] = {}


def modelo_padrao(config=None) -> str:
    if config is not None:
        escolhido = config.get("estudio", "modelo_transcricao", "")
        if escolhido:
            return escolhido
    return "large-v3-turbo" if shutil.which("nvidia-smi") else "small"


def _carregar(nome: str):
    if nome not in _MODELOS:
        try:
            from optimus.voice.stt import Ouvinte
        except ImportError as erro:  # pragma: no cover
            raise ErroEstudio(str(erro)) from erro
        try:
            _MODELOS[nome] = Ouvinte(nome)._carregar()
        except ImportError as erro:
            raise ErroEstudio("A transcrição precisa do faster-whisper: "
                              "pip install faster-whisper") from erro
    return _MODELOS[nome]


def transcrever(caminho: str | Path, idioma: str = "", modelo: str = "", config=None,
                progresso=None, cancelado=None) -> tuple[list[Trecho], idiomas.Idioma]:
    """Devolve (trechos com tempo, idioma falado)."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroEstudio(f"Arquivo não encontrado: {caminho}")
    whisper = _carregar(modelo or modelo_padrao(config))
    codigo = idiomas.idioma(idioma).whisper if idioma else None
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
            progresso(min(1.0, float(s.end) / total), f"Transcrevendo… {int(s.end)}s de "
                                                      f"{int(total)}s")
    falado = idiomas.idioma(idioma) if idioma else \
        idiomas.do_whisper(getattr(info, "language", "pt") or "pt")
    return trechos, falado


def descarregar() -> None:
    _MODELOS.clear()
