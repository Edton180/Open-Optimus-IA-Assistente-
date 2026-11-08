"""Reconhecimento de voz offline (faster-whisper) e gravação do microfone."""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import unicodedata

from optimus.tools.base import no_android

TAXA = 16000

# Frases que o Whisper "inventa" quando só há ruído ou silêncio.
_ALUCINACOES = [
    "legendas pela comunidade amara.org", "obrigado por assistir", "inscreva-se no canal",
    "legenda adriana zanotto", "obrigada por assistir",
    "legendas por", "subtitles by", "thank you for watching", "...",
]


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


def limpar_transcricao(texto: str) -> str:
    texto = texto.strip()
    normal = _normal(texto).strip(" .!?")
    if not normal or any(normal.startswith(_normal(a).strip(" .")) for a in _ALUCINACOES
                         if _normal(a).strip(" .")):
        return ""
    return texto


class Ouvinte:
    def __init__(self, modelo: str = "small", idioma: str = "pt"):
        self.modelo_nome = modelo or "small"
        self.idioma = idioma
        self._modelo = None

    def _carregar(self):
        if self._modelo is None:
            from faster_whisper import WhisperModel

            dispositivo, tipo = "cpu", "int8"
            if shutil.which("nvidia-smi"):
                try:
                    import ctranslate2

                    if ctranslate2.get_cuda_device_count() > 0:
                        dispositivo, tipo = "cuda", "float16"
                except Exception:  # noqa: BLE001
                    pass
            self._modelo = WhisperModel(self.modelo_nome, device=dispositivo, compute_type=tipo)
        return self._modelo

    def transcrever(self, audio) -> str:
        """audio: numpy float32 16 kHz, bytes de arquivo (wav/webm/ogg/mp3) ou caminho."""
        if isinstance(audio, (bytes, bytearray)):
            audio = io.BytesIO(audio)
        segmentos, _ = self._carregar().transcribe(
            audio, language=self.idioma, vad_filter=True, beam_size=1,
            condition_on_previous_text=False)
        return limpar_transcricao(" ".join(s.text for s in segmentos))


def ouvir_android() -> str:
    """No Android (Termux:API) usa o reconhecimento de voz do próprio celular."""
    if not (no_android() and shutil.which("termux-speech-to-text")):
        return ""
    resultado = subprocess.run(["termux-speech-to-text"], capture_output=True, text=True,
                               check=False)
    return resultado.stdout.strip()


def gravar_ate_silencio(limiar: float = 0.012, silencio_segundos: float = 1.1,
                        espera_inicial: float = 8.0, maximo: float = 30.0):
    """Grava do microfone até a pessoa parar de falar. Devolve numpy float32 ou None."""
    import numpy as np
    import sounddevice as sd

    bloco = 1024
    por_segundo = TAXA / bloco
    quadros, silencio, falou = [], 0, False
    with sd.InputStream(samplerate=TAXA, channels=1, dtype="float32", blocksize=bloco) as fluxo:
        for indice in range(int(maximo * por_segundo)):
            dados, _ = fluxo.read(bloco)
            volume = float(np.sqrt(np.mean(dados ** 2)))
            if volume > limiar:
                falou, silencio = True, 0
            elif falou:
                silencio += 1
            if falou:
                quadros.append(dados.copy())
                if silencio > silencio_segundos * por_segundo:
                    break
            elif indice > espera_inicial * por_segundo:
                return None
    if not quadros:
        return None
    return np.concatenate(quadros).flatten()


def contem_palavra_ativacao(texto: str, palavra: str) -> tuple[bool, str]:
    """Procura a palavra de ativação (aceita variações comuns do Whisper)."""
    normal = _normal(texto)
    alvo = _normal(palavra or "optimus")
    variantes = {alvo, alvo.replace("us", "os"), alvo.replace("o", "ó"), "optimos", "otimus",
                 "optmus", "optimu"}
    for variante in variantes:
        achado = re.search(rf"\b{re.escape(variante)}\w*\b[,.!]?\s*", normal)
        if achado:
            return True, normal[achado.end():].strip()
    return False, ""
