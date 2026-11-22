"""Separar a voz da música (isolamento vocal) com o Demucs (MIT).

Útil para: limpar uma gravação antes de clonar a voz, fazer karaokê e, na dublagem, manter a
música e os efeitos do vídeo original por baixo da voz nova (`fundo="musica"`).
Opcional: `pip install demucs` (usa o PyTorch; com placa de vídeo é bem mais rápido).
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

from optimus.estudio import audio, pasta_estudio
from optimus.estudio.audio import ErroEstudio

MODELO = "htdemucs"


def instalado() -> bool:
    try:
        return importlib.util.find_spec("demucs") is not None
    except (ImportError, ValueError):
        return False


def separar(arquivo: str | Path, progresso=None) -> dict[str, Path]:
    """Devolve {"voz": caminho, "fundo": caminho} (WAV). Guarda o resultado para reusar."""
    arquivo = Path(arquivo)
    if not arquivo.exists():
        raise ErroEstudio(f"Arquivo não encontrado: {arquivo}")
    if not instalado():
        raise ErroEstudio("Para separar a voz da música, instale: pip install demucs")
    st = arquivo.stat()
    chave = hashlib.sha1(f"{arquivo.resolve()}|{st.st_size}|{int(st.st_mtime)}".encode()
                         ).hexdigest()[:12]
    pasta = pasta_estudio() / "separados" / f"{arquivo.stem[:30]}-{chave}"
    voz, fundo = pasta / "voz.wav", pasta / "fundo.wav"
    if voz.exists() and fundo.exists():
        return {"voz": voz, "fundo": fundo}
    pasta.mkdir(parents=True, exist_ok=True)
    entrada = pasta / "entrada.wav"
    audio._rodar(["-i", str(arquivo), "-vn", "-ac", "2", "-ar", "44100", str(entrada)])
    (progresso or (lambda *a: None))(0.2, "Separando a voz da música (pode demorar)…")
    r = subprocess.run([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", MODELO,
                        "-o", str(pasta), str(entrada)], capture_output=True, text=True,
                       check=False)
    saida = pasta / MODELO / "entrada"
    if r.returncode != 0 or not (saida / "vocals.wav").exists():
        detalhe = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["sem detalhes"]
        raise ErroEstudio(f"O Demucs falhou: {detalhe[0]}")
    (saida / "vocals.wav").replace(voz)
    (saida / "no_vocals.wav").replace(fundo)
    entrada.unlink(missing_ok=True)
    return {"voz": voz, "fundo": fundo}
