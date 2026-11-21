"""Câmeras ligadas por cabo (USB) e a câmera do notebook, no Windows, Linux e macOS.

Cada webcam vira uma câmera comum do Optimus, com id ``usb:N`` (N = 0, 1, 2...): aparece na
tela Casa ao vivo e no ``camera_foto``. Para tirar a foto usa o OpenCV se estiver instalado
(``pip install opencv-python``), senão o ffmpeg, que já é usado pelas câmeras rtsp.

A imagem nunca sai do computador: é lida, salva na pasta do Optimus e mostrada na tela.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from optimus.tools.base import sistema

_CACHE: dict[str, object] = {"quando": 0.0, "lista": []}
_VALIDADE = 30.0  # segundos: a lista de webcams não é refeita a cada atualização da tela


def entrada_ffmpeg(indice: int, so: str, nome: str = "") -> list[str]:
    """Argumentos de entrada do ffmpeg para a webcam N em cada sistema."""
    if so == "windows":
        return ["-f", "dshow", "-i", f"video={nome}"]
    if so == "macos":
        return ["-f", "avfoundation", "-framerate", "30", "-i", f"{indice}:none"]
    return ["-f", "v4l2", "-i", f"/dev/video{indice}"]


def ler_dispositivos(saida: str, so: str) -> list[str]:
    """Nomes das câmeras na listagem do ffmpeg (Windows: dshow; macOS: avfoundation)."""
    nomes: list[str] = []
    if so == "windows":
        # ffmpeg novo: [dshow @ ...] "Integrated Camera" (video)
        nomes = re.findall(r'"([^"]+)"\s+\(video\)', saida)
        if not nomes:  # ffmpeg antigo: uma seção "DirectShow video devices"
            secao = re.search(r"DirectShow video devices(.*?)(DirectShow audio devices|$)",
                              saida, re.DOTALL)
            if secao:
                nomes = [n for n in re.findall(r'\]\s+"([^"]+)"', secao.group(1))
                         if not n.startswith("@device")]
    elif so == "macos":
        secao = re.search(r"AVFoundation video devices:(.*?)(AVFoundation audio devices|$)",
                          saida, re.DOTALL)
        if secao:
            nomes = [n.strip() for n in re.findall(r"\]\s*\[\d+\]\s*(.+)", secao.group(1))
                     if not n.strip().lower().startswith("capture screen")]
    return nomes


def _linux(raiz: Path = Path("/sys/class/video4linux")) -> list[dict]:
    """Cada webcam cria dois /dev/videoN (imagem e metadados); só o de índice 0 é a câmera."""
    achadas = []
    for pasta in sorted(raiz.glob("video*"), key=lambda p: int(re.sub(r"\D", "", p.name) or 0)):
        try:
            if (pasta / "index").read_text().strip() not in ("", "0"):
                continue
            nome = (pasta / "name").read_text().strip()
        except OSError:
            nome = ""
        numero = int(re.sub(r"\D", "", pasta.name) or 0)
        achadas.append({"indice": numero, "nome": nome or f"Webcam {numero}"})
    return achadas


def listar(so: str | None = None, forcar: bool = False) -> list[dict]:
    """Webcams presentes agora: [{"indice": 0, "nome": "Integrated Camera"}, ...]."""
    so = so or sistema()
    if not forcar and time.monotonic() - float(_CACHE["quando"]) < _VALIDADE:
        return list(_CACHE["lista"])  # type: ignore[arg-type]
    if so == "linux":
        lista = _linux()
    elif so in ("windows", "macos") and shutil.which("ffmpeg"):
        if so == "windows":
            comando = ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow",
                       "-i", "dummy"]
        else:
            comando = ["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true",
                       "-i", ""]
        try:
            r = subprocess.run(comando, capture_output=True, text=True, timeout=10,
                               check=False)
            lista = [{"indice": i, "nome": n}
                     for i, n in enumerate(ler_dispositivos(r.stderr + r.stdout, so))]
        except (OSError, subprocess.TimeoutExpired):
            lista = []
    else:
        lista = []
    _CACHE.update(quando=time.monotonic(), lista=lista)
    return list(lista)


def _foto_opencv(indice: int) -> bytes | None:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return None
    captura = cv2.VideoCapture(indice)
    try:
        if not captura.isOpened():
            return None
        quadro = None
        for _ in range(8):  # as primeiras imagens saem escuras (ajuste automático da luz)
            ok, atual = captura.read()
            if ok:
                quadro = atual
        if quadro is None:
            return None
        ok, jpg = cv2.imencode(".jpg", quadro)
        return jpg.tobytes() if ok else None
    finally:
        captura.release()


def comando_foto(entrada: list[str]) -> list[str]:
    # -ss depois da entrada: descarta ~0,6 s até a câmera acertar a luz.
    return ["ffmpeg", "-loglevel", "error", *entrada, "-ss", "0.6", "-frames:v", "1",
            "-f", "image2", "-vcodec", "mjpeg", "-"]


def foto(indice: int, so: str | None = None) -> bytes:
    """Uma foto JPEG da webcam N. Levanta RuntimeError com o motivo se não der."""
    so = so or sistema()
    imagem = _foto_opencv(indice)
    if imagem:
        return imagem
    if not shutil.which("ffmpeg"):
        raise RuntimeError("Para usar a webcam instale o OpenCV (pip install opencv-python) "
                           "ou o ffmpeg.")
    nome = ""
    if so == "windows":
        nomes = {c["indice"]: c["nome"] for c in listar(so)}
        if indice not in nomes:
            raise RuntimeError(f"Não achei a webcam {indice}. Ela está ligada no cabo?")
        nome = nomes[indice]
    try:
        r = subprocess.run(comando_foto(entrada_ffmpeg(indice, so, nome)), capture_output=True,
                           timeout=20, check=False)
    except subprocess.TimeoutExpired as erro:
        raise RuntimeError("A webcam não respondeu a tempo (outro programa está usando?)") \
            from erro
    if not r.stdout:
        motivo = r.stderr.decode(errors="replace").strip().splitlines()
        raise RuntimeError("Não consegui ler a webcam: " + (motivo[-1] if motivo else
                                                            "sem imagem"))
    return r.stdout
