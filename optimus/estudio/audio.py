"""Áudio e vídeo com o ffmpeg: abrir qualquer formato, salvar WAV/MP3/FLAC/M4A/OGG, ajustar a
duração sem mudar o tom, montar a faixa dublada e juntar com o vídeo (com ou sem legenda).

O ffmpeg vem do sistema ou do pacote `imageio-ffmpeg` (extra `[estudio]`).
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import wave
from pathlib import Path

FORMATOS = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus")
VIDEOS = (".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v")
MARCA_IA = "Voz gerada por IA (Open Optimus)"


class ErroEstudio(RuntimeError):
    pass


def ffmpeg() -> str:
    caminho = shutil.which("ffmpeg")
    if caminho:
        return caminho
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as erro:
        raise ErroEstudio("Preciso do ffmpeg para áudio e vídeo. Instale com "
                          "'pip install imageio-ffmpeg' ou baixe em ffmpeg.org.") from erro


def _rodar(args: list[str], entrada: bytes | None = None) -> bytes:
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                       input=entrada, capture_output=True, check=False)
    if r.returncode != 0:
        detalhe = r.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise ErroEstudio("O ffmpeg falhou: " + " | ".join(detalhe))
    return r.stdout


# ---------------------------------------------------------------------- abrir e salvar
def carregar(caminho: str | Path, taxa: int = 24000):
    """Qualquer áudio ou vídeo vira numpy float32 mono na taxa pedida."""
    import numpy as np

    if not Path(caminho).exists():
        raise ErroEstudio(f"Arquivo não encontrado: {caminho}")
    bruto = _rodar(["-i", str(caminho), "-vn", "-ac", "1", "-ar", str(taxa), "-f", "f32le", "-"])
    return np.frombuffer(bruto, dtype="<f4").copy()


def wav_bytes(amostras, taxa: int) -> bytes:
    import numpy as np

    dados = (np.clip(np.asarray(amostras, dtype="float32"), -1, 1) * 32767).astype("<i2")
    saida = io.BytesIO()
    with wave.open(saida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(dados.tobytes())
    return saida.getvalue()


def ler_wav(dados: bytes):
    """WAV (bytes) para (numpy float32 mono, taxa). Sem ffmpeg."""
    import numpy as np

    with wave.open(io.BytesIO(dados), "rb") as w:
        taxa, canais, largura = w.getframerate(), w.getnchannels(), w.getsampwidth()
        bruto = w.readframes(w.getnframes())
    if largura != 2:
        raise ErroEstudio("WAV precisa ser de 16 bits.")
    x = np.frombuffer(bruto, dtype="<i2").astype("float32") / 32768
    if canais > 1:
        x = x.reshape(-1, canais).mean(axis=1)
    return x, taxa


def salvar(amostras, taxa: int, caminho: str | Path, marca_ia: bool = True,
           titulo: str = "") -> Path:
    """Salva no formato da extensão. Áudio gerado leva a etiqueta 'gerado por IA'."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wav = wav_bytes(amostras, taxa)
    ext = caminho.suffix.lower()
    if ext == ".wav" and not (marca_ia or titulo):
        caminho.write_bytes(wav)
        return caminho
    if ext not in FORMATOS:
        raise ErroEstudio(f"Formato {ext} não suportado. Use: {', '.join(FORMATOS)}")
    meta = []
    if marca_ia:
        meta += ["-metadata", f"comment={MARCA_IA}"]
    if titulo:
        meta += ["-metadata", f"title={titulo}"]
    codec = {".mp3": ["-c:a", "libmp3lame", "-q:a", "2"], ".m4a": ["-c:a", "aac", "-b:a", "192k"],
             ".ogg": ["-c:a", "libvorbis", "-q:a", "5"], ".opus": ["-c:a", "libopus"],
             ".flac": ["-c:a", "flac"], ".wav": ["-c:a", "pcm_s16le"]}[ext]
    try:
        _rodar(["-f", "wav", "-i", "-", *meta, *codec, str(caminho)], entrada=wav)
    except ErroEstudio:
        if ext != ".wav":
            raise
        caminho.write_bytes(wav)  # sem ffmpeg: WAV simples, sem etiqueta
    return caminho


def duracao(caminho: str | Path) -> float:
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(caminho)], capture_output=True,
                       check=False)
    achado = re.search(rb"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not achado:
        raise ErroEstudio(f"Não consegui ler a duração de {caminho}")
    h, m, s = achado.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def eh_video(caminho: str | Path) -> bool:
    return Path(caminho).suffix.lower() in VIDEOS


# ---------------------------------------------------------------------- ajustes
def normalizar(amostras, pico: float = 0.9):
    import numpy as np

    x = np.asarray(amostras, dtype="float32")
    maior = float(np.max(np.abs(x))) if len(x) else 0.0
    return x if maior < 1e-6 else x / maior * pico


def cortar_silencio(amostras, taxa: int, limiar: float = 0.01):
    """Tira o silêncio do começo e do fim (motores de voz costumam deixar sobras)."""
    import numpy as np

    x = np.asarray(amostras, dtype="float32")
    acima = np.where(np.abs(x) > limiar)[0]
    if not len(acima):
        return x[:0]
    margem = int(taxa * 0.03)
    return x[max(0, acima[0] - margem): acima[-1] + margem]


def _cadeia_atempo(fator: float) -> str:
    filtros = []
    while fator > 2.0:
        filtros.append("atempo=2.0")
        fator /= 2.0
    while fator < 0.5:
        filtros.append("atempo=0.5")
        fator /= 0.5
    filtros.append(f"atempo={fator:.4f}")
    return ",".join(filtros)


def esticar(amostras, taxa: int, fator: float):
    """Fala mais rápido (fator > 1) ou mais devagar (< 1) sem mudar o tom da voz."""
    import numpy as np

    if abs(fator - 1.0) < 0.01 or not len(amostras):
        return np.asarray(amostras, dtype="float32")
    bruto = _rodar(["-f", "wav", "-i", "-", "-filter:a", _cadeia_atempo(fator), "-ac", "1",
                    "-ar", str(taxa), "-f", "f32le", "-"], entrada=wav_bytes(amostras, taxa))
    return np.frombuffer(bruto, dtype="<f4").copy()


def caber(amostras, taxa: int, segundos: float, acelerar_max: float = 1.35):
    """Faz a fala caber no tempo da legenda: acelera até `acelerar_max` e, se ainda sobrar,
    deixa passar um pouco (melhor que voz de esquilo). Devolve (amostras, fator usado)."""
    atual = len(amostras) / taxa
    if segundos <= 0 or atual <= segundos:
        return amostras, 1.0
    fator = min(acelerar_max, atual / segundos)
    return esticar(amostras, taxa, fator), fator


def linha_do_tempo(pedacos: list[tuple[float, object]], taxa: int, total: float = 0.0):
    """Coloca cada pedaço de fala no seu tempo. Pedaços que se sobrepõem são somados."""
    import numpy as np

    fim = max([ini + len(a) / taxa for ini, a in pedacos] + [total])
    faixa = np.zeros(int(fim * taxa) + 1, dtype="float32")
    for ini, a in pedacos:
        a = np.asarray(a, dtype="float32")
        p = int(ini * taxa)
        faixa[p:p + len(a)] += a
    return np.clip(faixa, -1, 1)


# ---------------------------------------------------------------------- vídeo
def extrair_audio(video: str | Path, destino: str | Path, taxa: int = 16000) -> Path:
    _rodar(["-i", str(video), "-vn", "-ac", "1", "-ar", str(taxa), str(destino)])
    return Path(destino)


def _escapar_filtro(caminho: Path) -> str:
    # o filtro subtitles do ffmpeg tem regras próprias para ':' e '\' (C:\ no Windows)
    return str(caminho.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def estilo_legenda(tamanho: int = 22, cor: str = "branca", fundo: bool = True) -> str:
    cores = {"branca": "&H00FFFFFF", "amarela": "&H0000FFFF", "preta": "&H00000000"}
    estilo = f"FontSize={tamanho},PrimaryColour={cores.get(cor, cores['branca'])},Outline=2"
    return estilo + (",BorderStyle=3,BackColour=&H80000000" if fundo else "")


def juntar_video(video: str | Path, saida: str | Path, voz: str | Path | None = None,
                 volume_original: float = 0.15, legenda: str | Path | None = None,
                 queimar: bool = False, estilo: str = "") -> Path:
    """Junta a faixa de voz ao vídeo (o áudio original fica baixinho por baixo, ou some com
    volume 0) e põe a legenda: queimada na imagem ou como faixa que liga e desliga."""
    video, saida = Path(video), Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", str(video)]
    if voz:
        args += ["-i", str(voz)]
    sub_como_faixa = legenda and not queimar
    if sub_como_faixa:
        args += ["-i", str(legenda)]
    filtros, mapas = [], ["-map", "0:v:0"]
    if queimar and legenda:
        f = f"subtitles='{_escapar_filtro(Path(legenda))}'"
        if estilo:
            f += f":force_style='{estilo}'"
        filtros.append(f"[0:v]{f}[v]")
        mapas = ["-map", "[v]"]
    if voz:
        if volume_original > 0:
            filtros.append(f"[0:a]volume={volume_original}[fundo];"
                           "[fundo][1:a]amix=inputs=2:duration=first:normalize=0[a]")
            mapas += ["-map", "[a]"]
        else:
            mapas += ["-map", "1:a:0"]
    else:
        mapas += ["-map", "0:a?"]
    if sub_como_faixa:
        mapas += ["-map", f"{2 if voz else 1}:s:0"]
    if filtros:
        args += ["-filter_complex", ";".join(filtros)]
    args += mapas
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"] if queimar and legenda \
        else ["-c:v", "copy"]
    args += ["-c:a", "aac", "-b:a", "192k"]
    if sub_como_faixa:
        args += ["-c:s", "mov_text" if saida.suffix.lower() in (".mp4", ".m4v", ".mov")
                 else "srt", "-metadata:s:s:0", "language=por"]
    if voz:
        args += ["-metadata", f"comment={MARCA_IA}"]
    args.append(str(saida))
    _rodar(args)
    return saida
