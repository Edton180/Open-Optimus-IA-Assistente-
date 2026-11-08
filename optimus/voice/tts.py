"""Fala (texto para voz) com vozes masculinas e femininas prontas.

Motores, do mais natural ao mais simples:
- kokoro: vozes neurais OFFLINE em português (pf_dora feminina, pm_alex e pm_santa
  masculinas). O instalador já baixa os arquivos (cerca de 120 MB), então funciona sem
  internet desde o primeiro uso.
- edge: vozes neurais da Microsoft pela internet (Francisca, Thalita, Antonio). Não
  precisa baixar nada, só estar online.
- sistema: vozes do próprio sistema (Windows: Maria/Daniel; Linux: espeak-ng). Sempre há
  uma disponível.
- termux: no Android, usa o motor de voz do próprio celular (Termux:API).

A configuração [voz] voz aceita "feminina", "masculina" ou um id da lista VOZES.
"""

from __future__ import annotations

import asyncio
import io
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

from optimus.config import pasta_base
from optimus.tools.base import no_android

URL_KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
ARQUIVOS_KOKORO = ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")


@dataclass(frozen=True)
class Voz:
    id: str
    nome: str
    genero: str  # feminina | masculina
    motor: str
    offline: bool
    descricao: str


VOZES: list[Voz] = [
    Voz("kokoro:pf_dora", "Dora", "feminina", "kokoro", True, "Feminina natural, offline"),
    Voz("kokoro:pm_alex", "Alex", "masculina", "kokoro", True, "Masculina natural, offline"),
    Voz("kokoro:pm_santa", "Santa", "masculina", "kokoro", True, "Masculina grave, offline"),
    Voz("edge:pt-BR-FranciscaNeural", "Francisca", "feminina", "edge", False,
        "Feminina neural, online"),
    Voz("edge:pt-BR-ThalitaMultilingualNeural", "Thalita", "feminina", "edge", False,
        "Feminina neural multilíngue, online"),
    Voz("edge:pt-BR-AntonioNeural", "Antonio", "masculina", "edge", False,
        "Masculina neural, online"),
    Voz("sistema:feminina", "Sistema (feminina)", "feminina", "sistema", True,
        "Voz instalada no sistema"),
    Voz("sistema:masculina", "Sistema (masculina)", "masculina", "sistema", True,
        "Voz instalada no sistema"),
]


def pasta_vozes() -> Path:
    return pasta_base() / "vozes"


def kokoro_instalado() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return False
    return all((pasta_vozes() / nome).exists() for nome in ARQUIVOS_KOKORO)


def edge_instalado() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def baixar_kokoro(progresso=None) -> bool:
    import httpx

    pasta_vozes().mkdir(parents=True, exist_ok=True)
    for nome in ARQUIVOS_KOKORO:
        destino = pasta_vozes() / nome
        if destino.exists() and destino.stat().st_size > 1_000_000:
            continue
        temporario = destino.with_suffix(".parcial")
        with httpx.stream("GET", URL_KOKORO + nome, follow_redirects=True, timeout=None) as r:
            if r.status_code != 200:
                return False
            total = int(r.headers.get("content-length", 0))
            baixado = 0
            with open(temporario, "wb") as arquivo:
                for pedaco in r.iter_bytes(1 << 20):
                    arquivo.write(pedaco)
                    baixado += len(pedaco)
                    if progresso:
                        progresso(nome, baixado, total)
        temporario.replace(destino)
    return True


def escolher_voz(preferencia: str, online: bool = True) -> Voz:
    """'feminina'/'masculina'/id → a melhor voz disponível neste PC."""
    preferencia = (preferencia or "feminina").strip()
    por_id = {v.id: v for v in VOZES}
    if preferencia in por_id:
        voz = por_id[preferencia]
        if (voz.motor == "kokoro" and kokoro_instalado()) or \
                (voz.motor == "edge" and edge_instalado() and online) or voz.motor == "sistema":
            return voz
        preferencia = voz.genero
    genero = "masculina" if preferencia.startswith("mascul") else "feminina"
    candidatas = [v for v in VOZES if v.genero == genero]
    for voz in candidatas:
        if voz.motor == "kokoro" and kokoro_instalado():
            return voz
    for voz in candidatas:
        if voz.motor == "edge" and edge_instalado() and online:
            return voz
    return por_id[f"sistema:{genero}"]


def dividir_frases(texto: str) -> list[str]:
    texto = re.sub(r"```.*?```", " (código na tela) ", texto, flags=re.DOTALL)
    texto = re.sub(r"[*_#`>|]+", "", texto)
    texto = re.sub(r"https?://\S+", "link", texto)
    partes = re.split(r"(?<=[.!?;:])\s+|\n+", texto)
    return [p.strip() for p in partes if len(p.strip()) > 1]


def _wav_bytes(amostras, taxa: int) -> bytes:
    import numpy as np

    dados = (np.clip(amostras, -1, 1) * 32767).astype("<i2").tobytes()
    saida = io.BytesIO()
    with wave.open(saida, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(taxa)
        wav.writeframes(dados)
    return saida.getvalue()


class Falante:
    """Gera e toca a fala. Pode ser interrompido com parar()."""

    def __init__(self, voz: str = "feminina", velocidade: float = 1.0, online: bool = True):
        self.voz = escolher_voz(voz, online)
        self.velocidade = float(velocidade or 1.0)
        self._kokoro = None
        self._parar = threading.Event()

    # Síntese
    def sintetizar(self, texto: str) -> tuple[bytes, str]:
        """Devolve (áudio, formato) com formato 'wav' ou 'mp3'."""
        motor = self.voz.motor
        if motor == "kokoro":
            return self._kokoro_wav(texto), "wav"
        if motor == "edge":
            try:
                return self._edge_mp3(texto), "mp3"
            except Exception:  # noqa: BLE001 - sem internet: cai para a voz offline
                self.voz = escolher_voz(self.voz.genero, online=False)
                return self.sintetizar(texto)
        return self._sistema_wav(texto), "wav"

    def _kokoro_wav(self, texto: str) -> bytes:
        if self._kokoro is None:
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(str(pasta_vozes() / ARQUIVOS_KOKORO[0]),
                                  str(pasta_vozes() / ARQUIVOS_KOKORO[1]))
        amostras, taxa = self._kokoro.create(texto, voice=self.voz.id.split(":", 1)[1],
                                             speed=self.velocidade, lang="pt-br")
        return _wav_bytes(amostras, taxa)

    def _edge_mp3(self, texto: str) -> bytes:
        import edge_tts

        taxa = f"{int(round((self.velocidade - 1) * 100)):+d}%"

        async def gerar() -> bytes:
            comunicador = edge_tts.Communicate(texto, self.voz.id.split(":", 1)[1], rate=taxa)
            pedacos = []
            async for parte in comunicador.stream():
                if parte["type"] == "audio":
                    pedacos.append(parte["data"])
            return b"".join(pedacos)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(gerar())
        resultado: list[bytes] = []
        linha = threading.Thread(target=lambda: resultado.append(asyncio.run(gerar())))
        linha.start()
        linha.join()
        return resultado[0]

    def _sistema_wav(self, texto: str) -> bytes:
        if no_android() and shutil.which("termux-tts-speak"):
            subprocess.run(["termux-tts-speak", "-l", "pt", "-r", str(self.velocidade), texto],
                           check=False)
            return b""
        if shutil.which("espeak-ng") or shutil.which("espeak"):
            programa = shutil.which("espeak-ng") or shutil.which("espeak")
            variante = "pt-br+f3" if self.voz.genero == "feminina" else "pt-br+m3"
            resultado = subprocess.run(
                [programa, "-v", variante, "-s", str(int(165 * self.velocidade)), "--stdout",
                 texto], capture_output=True, check=False)
            return resultado.stdout
        import pyttsx3

        motor = pyttsx3.init()
        vozes = motor.getProperty("voices")
        preferidas = ("maria", "francisca", "helena", "luciana", "zira") \
            if self.voz.genero == "feminina" else ("daniel", "antonio", "ricardo", "david")
        for nome in preferidas:
            achada = next((v for v in vozes if nome in (v.name or "").lower()), None)
            if achada:
                motor.setProperty("voice", achada.id)
                break
        motor.setProperty("rate", int(180 * self.velocidade))
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "fala.wav"
            motor.save_to_file(texto, str(destino))
            motor.runAndWait()
            return destino.read_bytes() if destino.exists() else b""

    # Reprodução
    def parar(self) -> None:
        self._parar.set()

    def falar(self, texto: str) -> None:
        """Fala frase por frase; a próxima frase é gerada enquanto a atual toca."""
        self._parar.clear()
        for frase in dividir_frases(texto):
            if self._parar.is_set():
                break
            audio, formato = self.sintetizar(frase)
            if audio:
                tocar(audio, formato, self._parar)


def tocar(audio: bytes, formato: str, parar: threading.Event | None = None) -> None:
    try:
        import miniaudio
    except ImportError:
        miniaudio = None
    if miniaudio:
        decodificado = miniaudio.decode(audio, output_format=miniaudio.SampleFormat.SIGNED16)
        terminou = threading.Event()
        quadros = decodificado.samples
        canais = decodificado.nchannels
        posicao = 0

        def gerador():
            nonlocal posicao
            pedido = yield b""
            while posicao < len(quadros):
                if parar is not None and parar.is_set():
                    break
                fim = posicao + pedido * canais
                pedido = yield quadros[posicao:fim]
                posicao = fim
            terminou.set()

        fluxo = gerador()
        next(fluxo)
        with miniaudio.PlaybackDevice(output_format=miniaudio.SampleFormat.SIGNED16,
                                      nchannels=canais,
                                      sample_rate=decodificado.sample_rate) as dispositivo:
            dispositivo.start(fluxo)
            terminou.wait(timeout=len(quadros) / canais / decodificado.sample_rate + 2)
        return
    for player in (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], ["mpv"],
                   ["aplay", "-q"], ["paplay"]):
        if shutil.which(player[0]):
            with tempfile.NamedTemporaryFile(suffix="." + formato, delete=False) as arquivo:
                arquivo.write(audio)
            subprocess.run([*player, arquivo.name], check=False)
            Path(arquivo.name).unlink(missing_ok=True)
            return
