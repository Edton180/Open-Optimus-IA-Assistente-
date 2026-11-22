"""Vozes Piper offline (pelo sherpa-onnx): leves, rápidas no CPU e sem internet depois de baixar.

Inclui quatro vozes em português do Brasil (Faber, Cadu, Jeff e Edresson) e vozes de outros
idiomas. Cada voz tem de 20 a 75 MB e vem do GitHub do sherpa-onnx na primeira vez.

Precisa de `pip install "sherpa-onnx>=1.10,<2"` (a série 2.x ainda não lê o espeak das vozes
Piper sozinha).
"""

from __future__ import annotations

import importlib.util
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

from optimus.estudio import pasta_estudio
from optimus.estudio.audio import ErroEstudio

BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"


@dataclass(frozen=True)
class VozPiper:
    id: str  # nome do pacote, ex. pt_BR-faber-medium
    nome: str
    idioma: str
    genero: str
    tamanho_mb: int
    licenca: str = "ver MODEL_CARD"

    @property
    def perfil_id(self) -> str:
        return "piper-" + self.id.split("-")[1]


VOZES = [
    VozPiper("pt_BR-faber-medium", "Faber (Piper)", "pt-BR", "masculina", 64, "CC0"),
    VozPiper("pt_BR-cadu-medium", "Cadu (Piper)", "pt-BR", "masculina", 64),
    VozPiper("pt_BR-jeff-medium", "Jeff (Piper)", "pt-BR", "masculina", 64),
    VozPiper("pt_BR-edresson-low", "Edresson (Piper)", "pt-BR", "masculina", 64),
    VozPiper("pt_PT-tugao-medium", "Tugão (Piper, Portugal)", "pt-PT", "masculina", 64),
    VozPiper("en_US-amy-medium", "Amy (Piper, inglês)", "en-US", "feminina", 64),
    VozPiper("es_ES-davefx-medium", "Davefx (Piper, espanhol)", "es", "masculina", 64),
    VozPiper("fr_FR-siwis-medium", "Siwis (Piper, francês)", "fr", "feminina", 64),
    VozPiper("de_DE-thorsten-medium", "Thorsten (Piper, alemão)", "de", "masculina", 64),
    VozPiper("it_IT-riccardo-x_low", "Riccardo (Piper, italiano)", "it", "masculina", 28),
]
_POR_ID = {v.id: v for v in VOZES} | {v.perfil_id: v for v in VOZES}
_TTS: dict[str, object] = {}
_TRAVA = threading.Lock()


def instalado() -> bool:
    try:
        return importlib.util.find_spec("sherpa_onnx") is not None
    except (ImportError, ValueError):
        return False


def pasta() -> Path:
    return pasta_estudio() / "modelos" / "piper"


def voz(ident: str) -> VozPiper:
    v = _POR_ID.get(ident) or _POR_ID.get(ident.replace("vits-piper-", ""))
    if not v:
        raise ErroEstudio(f"Voz Piper desconhecida: {ident}. Vozes: "
                          + ", ".join(x.id for x in VOZES))
    return v


def pasta_voz(v: VozPiper) -> Path:
    return pasta() / f"vits-piper-{v.id}"


def baixada(v: VozPiper) -> bool:
    return (pasta_voz(v) / f"{v.id}.onnx").exists()


def baixar(ident: str, progresso=None) -> Path:
    from optimus.estudio.transcrever import _baixar, _extrair

    v = voz(ident)
    if baixada(v):
        return pasta_voz(v)
    pacote = pasta() / f"vits-piper-{v.id}.tar.bz2"
    _baixar(BASE + pacote.name, pacote, progresso, f"Baixando a voz {v.nome}…")
    try:
        _extrair(pacote, pasta())
    finally:
        pacote.unlink(missing_ok=True)
    if not baixada(v):
        raise ErroEstudio(f"O pacote da voz {v.nome} veio incompleto.")
    return pasta_voz(v)


def remover(ident: str) -> bool:
    v = voz(ident)
    with _TRAVA:
        _TTS.pop(v.id, None)
    if pasta_voz(v).exists():
        shutil.rmtree(pasta_voz(v), ignore_errors=True)
        return True
    return False


def _motor(v: VozPiper):
    if not instalado():
        raise ErroEstudio('As vozes Piper precisam do sherpa-onnx: pip install "sherpa-onnx<2"')
    with _TRAVA:
        if v.id not in _TTS:
            import sherpa_onnx

            d = pasta_voz(v)
            vits = sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(d / f"{v.id}.onnx"), tokens=str(d / "tokens.txt"),
                data_dir=str(d / "espeak-ng-data"))
            config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=2))
            _TTS[v.id] = sherpa_onnx.OfflineTts(config)
    return _TTS[v.id]


def gerar(texto: str, ident: str, velocidade: float = 1.0, progresso=None):
    """Texto → (numpy float32, taxa). Baixa a voz se ainda não tiver."""
    import numpy as np

    v = voz(ident)
    if not baixada(v):
        baixar(v.id, progresso)
    try:
        resultado = _motor(v).generate(texto, sid=0, speed=float(velocidade or 1.0))
    except Exception as erro:  # versão do sherpa-onnx sem o espeak
        raise ErroEstudio(f'A voz Piper falhou ({erro}). Use: pip install "sherpa-onnx<2"') \
            from erro
    x = np.asarray(resultado.samples, dtype="float32")
    if not len(x):
        raise ErroEstudio('A voz Piper não devolveu áudio. Use: pip install "sherpa-onnx<2"')
    return x, int(resultado.sample_rate)


def descarregar() -> None:
    with _TRAVA:
        _TTS.clear()
