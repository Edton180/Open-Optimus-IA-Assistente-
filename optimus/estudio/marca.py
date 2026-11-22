"""Marca d'água inaudível: todo áudio gerado pelo Estúdio leva um sinal escondido de "voz de IA".

Como funciona (código próprio, só numpy): um padrão pseudoaleatório, tirado de uma chave,
sobe e desce de leve (cerca de 1 dB) a força de cada faixa estreita de frequência entre
250 Hz e 7 kHz, sempre do mesmo jeito. O ouvido não percebe, mas, somando muitos quadros, o padrão
aparece claro na correlação. Sobrevive a MP3, AAC e mudança de volume.

`detectar()` não precisa do áudio original, só da mesma chave. O resultado é uma pontuação
(desvios-padrão acima do acaso): acima de 4, o áudio foi marcado com essa chave.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

CHAVE_PADRAO = "open-optimus-voz-ia"
QUADRO = 1024
FORCA = 0.12
LIMIAR = 4.0
_FAIXA = (250.0, 7000.0)


def _np():
    import numpy as np

    return np


def _quadro(taxa: int) -> int:
    """Tamanho do quadro que mantém cada bin com a mesma largura (~23 Hz) em qualquer taxa."""
    return max(256, int(round(taxa * QUADRO / 24000 / 2)) * 2)


def _padrao(chave: str, taxa: int):
    """±1 para cada faixa (grupos de 2 bins), igual em todos os quadros."""
    np = _np()
    bins = np.fft.rfftfreq(_quadro(taxa), 1 / taxa)
    usados = np.where((bins >= _FAIXA[0]) & (bins <= min(_FAIXA[1], taxa / 2 - 200)))[0]
    semente = int.from_bytes(hashlib.sha256(chave.encode()).digest()[:8], "little")
    sinais = np.random.default_rng(semente).choice([-1.0, 1.0], size=(len(usados) + 1) // 2)
    return usados, np.repeat(sinais, 2)[:len(usados)]


def marcar(amostras, taxa: int, chave: str = CHAVE_PADRAO):
    """Devolve as amostras com a marca (float32 mono, mesmo tamanho)."""
    np = _np()
    x = np.asarray(amostras, dtype=np.float32)
    quadro = _quadro(taxa)
    if len(x) < quadro * 4:
        return x
    usados, padrao = _padrao(chave, taxa)
    ganho = np.ones(quadro // 2 + 1, dtype=np.float64)
    ganho[usados] = 1.0 + FORCA * padrao
    salto = quadro // 2
    janela = np.sqrt(np.hanning(quadro + 1)[:quadro])  # raiz da Hann: soma perfeita a 50%
    resto = (-(len(x) - quadro) % salto) if len(x) > quadro else 0
    y = np.concatenate([np.zeros(salto, np.float32), x, np.zeros(salto + resto, np.float32)])
    saida = np.zeros_like(y, dtype=np.float64)
    for i in range(0, len(y) - quadro + 1, salto):
        espectro = np.fft.rfft(y[i:i + quadro] * janela)
        saida[i:i + quadro] += np.fft.irfft(espectro * ganho, quadro) * janela
    marcado = saida[salto:salto + len(x)]
    pico = float(np.max(np.abs(marcado))) or 1.0
    if pico > 0.999:
        marcado = marcado * (0.999 / pico)
    return marcado.astype(np.float32)


def pontuar(amostras, taxa: int, chave: str = CHAVE_PADRAO) -> float:
    """Quantos desvios-padrão acima do acaso está a correlação com o padrão da chave."""
    np = _np()
    x = np.asarray(amostras, dtype=np.float64)
    quadro = _quadro(taxa)
    if len(x) < quadro * 4:
        return 0.0
    usados, padrao = _padrao(chave, taxa)
    janela = np.hanning(quadro)
    residuos = []
    for i in range(0, len(x) - quadro + 1, quadro // 2):
        trecho = x[i:i + quadro]
        if np.sqrt(np.mean(trecho ** 2)) < 1e-3:  # silêncio não carrega a marca
            continue
        espectro = np.log(np.abs(np.fft.rfft(trecho * janela))[usados] + 1e-9)
        suave = np.convolve(espectro, np.ones(9) / 9, mode="same")  # tira a "cor" da voz
        residuos.append((espectro - suave)[4:-4])
    if len(residuos) < 8:
        return 0.0
    residuos = np.array(residuos)
    # média de cada faixa dividida pela variação dela: faixas instáveis pesam menos
    estatistica = residuos.mean(axis=0) / (residuos.std(axis=0) + 1e-6)
    p = padrao[4:-4]
    if estatistica.std() == 0:
        return 0.0
    correlacao = float(np.corrcoef(estatistica, p)[0, 1])
    return round(float(correlacao * np.sqrt(len(p))), 2)


def detectar(arquivo: str | Path, chave: str = CHAVE_PADRAO) -> dict:
    """Lê um arquivo de áudio ou vídeo e diz se ele tem a marca de voz de IA do Optimus."""
    from optimus.estudio import audio

    taxa = 24000
    amostras = audio.carregar(arquivo, taxa)
    pontos = pontuar(amostras, taxa, chave)
    return {"arquivo": str(arquivo), "marcado": bool(pontos >= LIMIAR), "pontuacao": pontos,
            "limiar": LIMIAR}
