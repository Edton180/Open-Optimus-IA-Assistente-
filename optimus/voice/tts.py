"""Fala (texto para voz) com vozes prontas, masculinas e femininas, com nomes próprios.

Vozes do Optimus (o nome é o que aparece no painel e no comando "mude para a voz Nexus"):
- Prime: clássica e executiva (masculina), offline.
- Valkyrie: feminina fluida e natural, offline.
- Nexus: tom grave e analítico (masculina), offline.
- Cyber: sintética futurista, com efeito robótico, offline.
- Stealth: voz baixa e suave para a noite, offline.
- Elite: ultrarrealista pela API da ElevenLabs (precisa de chave).
- Aurora, Lyra e Titan: vozes neurais online (Microsoft Edge), sem chave.
- Sistema: a voz instalada no Windows/Linux/Android, sempre disponível.

As vozes offline usam o Kokoro (o instalador já baixa, cerca de 120 MB). Se uma voz não
estiver disponível no PC, o Optimus usa a reserva mais parecida sem travar.
"""

from __future__ import annotations

import asyncio
import io
import re
import shutil
import subprocess
import tempfile
import threading
import unicodedata
import wave
from dataclasses import dataclass, field
from pathlib import Path

from optimus.config import pasta_base
from optimus.tools.base import no_android

URL_KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
ARQUIVOS_KOKORO = ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
URL_ELEVENLABS = "https://api.elevenlabs.io/v1/text-to-speech/"
# "Daniel": voz masculina madura e elegante da biblioteca padrão da ElevenLabs.
VOZ_ELEVENLABS_PADRAO = "onwK4e9ZLuTAKqWW03F9"


@dataclass(frozen=True)
class Voz:
    id: str
    nome: str
    genero: str  # feminina | masculina
    motor: str  # kokoro | edge | elevenlabs | sistema
    offline: bool
    descricao: str
    base: str = ""  # voz no motor (pm_alex, pt-BR-AntonioNeural...)
    efeito: str = ""  # "" | cyber | sussurro
    velocidade: float = 1.0
    reservas: tuple[str, ...] = field(default=())


VOZES: list[Voz] = [
    Voz("prime", "Prime", "masculina", "kokoro", True, "Clássica e executiva",
        "pm_alex", reservas=("titan", "sistema-masculina")),
    Voz("valkyrie", "Valkyrie", "feminina", "kokoro", True, "Feminina fluida e natural",
        "pf_dora", reservas=("aurora", "sistema-feminina")),
    Voz("nexus", "Nexus", "masculina", "kokoro", True, "Tom grave e analítico",
        "pm_santa", velocidade=0.95, reservas=("titan", "sistema-masculina")),
    Voz("cyber", "Cyber", "masculina", "kokoro", True, "Sintética futurista (efeito robótico)",
        "pm_alex", efeito="cyber", velocidade=1.05, reservas=("sistema-masculina",)),
    Voz("stealth", "Stealth", "feminina", "kokoro", True, "Sussurro: baixa e suave, modo noturno",
        "pf_dora", efeito="sussurro", velocidade=0.9, reservas=("sistema-feminina",)),
    Voz("elite", "Elite", "masculina", "elevenlabs", False,
        "Ultrarrealista pela ElevenLabs (precisa de chave)", VOZ_ELEVENLABS_PADRAO,
        reservas=("prime", "titan", "sistema-masculina")),
    Voz("aurora", "Aurora", "feminina", "edge", False, "Feminina neural, online",
        "pt-BR-FranciscaNeural", reservas=("valkyrie", "sistema-feminina")),
    Voz("lyra", "Lyra", "feminina", "edge", False, "Feminina neural multilíngue, online",
        "pt-BR-ThalitaMultilingualNeural", reservas=("valkyrie", "sistema-feminina")),
    Voz("titan", "Titan", "masculina", "edge", False, "Masculina neural, online",
        "pt-BR-AntonioNeural", reservas=("prime", "sistema-masculina")),
    Voz("sistema-feminina", "Sistema (feminina)", "feminina", "sistema", True,
        "Voz feminina instalada no sistema"),
    Voz("sistema-masculina", "Sistema (masculina)", "masculina", "sistema", True,
        "Voz masculina instalada no sistema"),
]

# Nomes antigos (v0.1) e atalhos continuam funcionando.
APELIDOS = {
    "feminina": "valkyrie", "masculina": "prime",
    "kokoro:pf_dora": "valkyrie", "kokoro:pm_alex": "prime", "kokoro:pm_santa": "nexus",
    "edge:pt-BR-FranciscaNeural": "aurora", "edge:pt-BR-ThalitaMultilingualNeural": "lyra",
    "edge:pt-BR-AntonioNeural": "titan", "sistema:feminina": "sistema-feminina",
    "sistema:masculina": "sistema-masculina", "valquiria": "valkyrie", "valquíria": "valkyrie",
    "eleven": "elite", "elevenlabs": "elite", "sistema": "sistema-feminina",
}

POR_ID = {v.id: v for v in VOZES}


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


def buscar_voz(nome: str) -> Voz | None:
    """Acha uma voz pelo id, nome ou apelido ("Nexus", "valquíria", "kokoro:pm_alex")."""
    chave = (nome or "").strip()
    if chave in POR_ID:
        return POR_ID[chave]
    if chave in APELIDOS:
        return POR_ID[APELIDOS[chave]]
    normal = _normal(chave)
    for voz in VOZES:
        if normal in (_normal(voz.id), _normal(voz.nome)):
            return voz
    if normal in APELIDOS:
        return POR_ID[APELIDOS[normal]]
    return None


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


def voz_disponivel(voz: Voz, online: bool = True, chave_elevenlabs: str = "") -> bool:
    if voz.motor == "kokoro":
        return kokoro_instalado()
    if voz.motor == "edge":
        return online and edge_instalado()
    if voz.motor == "elevenlabs":
        return online and bool(chave_elevenlabs)
    return True


def escolher_voz(preferencia: str, online: bool = True, chave_elevenlabs: str = "") -> Voz:
    """Nome, id ou gênero → a melhor voz disponível neste PC (com reservas)."""
    pedida = buscar_voz(preferencia or "valkyrie") or POR_ID["valkyrie"]
    fila = [pedida.id, *pedida.reservas]
    for ident in fila:
        voz = POR_ID[ident]
        if voz_disponivel(voz, online, chave_elevenlabs):
            return voz
    return POR_ID[f"sistema-{pedida.genero}"]


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


def _ler_wav(dados: bytes):
    import numpy as np

    with wave.open(io.BytesIO(dados), "rb") as wav:
        taxa, canais = wav.getframerate(), wav.getnchannels()
        largura = wav.getsampwidth()
        bruto = wav.readframes(wav.getnframes())
    if largura != 2:
        return None, taxa
    amostras = np.frombuffer(bruto, dtype="<i2").astype("float32") / 32768
    if canais > 1:
        amostras = amostras.reshape(-1, canais).mean(axis=1)
    return amostras, taxa


def aplicar_efeito(amostras, taxa: int, efeito: str):
    """Efeitos das vozes Cyber (robótica) e Stealth (baixa e abafada)."""
    import numpy as np

    if not efeito or amostras is None or len(amostras) == 0:
        return amostras
    x = amostras.astype("float32")
    if efeito == "cyber":
        t = np.arange(len(x), dtype="float32") / taxa
        robo = x * np.sin(2 * np.pi * 70 * t)
        y = 0.55 * x + 0.45 * robo
        atraso = int(taxa * 0.012)
        eco = np.zeros_like(y)
        eco[atraso:] = y[:-atraso] * 0.35
        y = y + eco
        y = np.round(y * 48) / 48  # leve "bitcrush"
    elif efeito == "sussurro":
        nucleo = np.ones(7, dtype="float32") / 7  # passa-baixa simples: tira o brilho da voz
        y = np.convolve(x, nucleo, mode="same") * 0.5
        return np.clip(y, -1, 1)
    else:
        return x
    pico = float(np.max(np.abs(y))) or 1.0
    return np.clip(y / pico * 0.9, -1, 1)


class Falante:
    """Gera e toca a fala. Pode ser interrompido com parar().

    `config` (opcional) traz a chave e a voz da ElevenLabs para a voz Elite.
    """

    def __init__(self, voz: str = "valkyrie", velocidade: float = 1.0, online: bool = True,
                 config=None):
        voz_cfg = (config.dados.get("voz", {}) if config is not None else {}) or {}
        self.chave_elevenlabs = voz_cfg.get("elevenlabs_chave", "") or ""
        self.voz_elevenlabs = voz_cfg.get("elevenlabs_voz", "") or VOZ_ELEVENLABS_PADRAO
        self.pedida = voz
        self.voz = escolher_voz(voz, online, self.chave_elevenlabs)
        # O efeito (Cyber, Stealth) continua mesmo quando a voz cai para uma reserva.
        self.efeito = (buscar_voz(voz) or self.voz).efeito
        self.velocidade = float(velocidade or 1.0)
        self._kokoro = None
        self._parar = threading.Event()
        self.ao_nivel = None  # callback(nível 0..1) para o orbe da interface

    # Síntese
    def sintetizar(self, texto: str) -> tuple[bytes, str]:
        """Devolve (áudio, formato) com formato 'wav' ou 'mp3'."""
        motor = self.voz.motor
        if motor == "kokoro":
            return self._com_efeito(self._kokoro_wav(texto)), "wav"
        if motor in ("edge", "elevenlabs"):
            try:
                if motor == "edge":
                    return self._edge_mp3(texto), "mp3"
                return self._elevenlabs_mp3(texto), "mp3"
            except Exception:  # noqa: BLE001 - sem internet ou sem crédito: usa a reserva
                reserva = next((POR_ID[r] for r in self.voz.reservas
                                if POR_ID[r].motor not in ("edge", "elevenlabs")
                                and voz_disponivel(POR_ID[r], False)), None)
                self.voz = reserva or POR_ID[f"sistema-{self.voz.genero}"]
                return self.sintetizar(texto)
        return self._com_efeito(self._sistema_wav(texto)), "wav"

    def _com_efeito(self, audio: bytes) -> bytes:
        if not self.efeito or not audio:
            return audio
        try:
            amostras, taxa = _ler_wav(audio)
            if amostras is None:
                return audio
            return _wav_bytes(aplicar_efeito(amostras, taxa, self.efeito), taxa)
        except Exception:  # noqa: BLE001
            return audio

    def _kokoro_wav(self, texto: str) -> bytes:
        if self._kokoro is None:
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(str(pasta_vozes() / ARQUIVOS_KOKORO[0]),
                                  str(pasta_vozes() / ARQUIVOS_KOKORO[1]))
        amostras, taxa = self._kokoro.create(texto, voice=self.voz.base,
                                             speed=self.velocidade * self.voz.velocidade,
                                             lang="pt-br")
        return _wav_bytes(amostras, taxa)

    def _elevenlabs_mp3(self, texto: str) -> bytes:
        import httpx

        resposta = httpx.post(
            URL_ELEVENLABS + self.voz_elevenlabs, params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self.chave_elevenlabs, "Content-Type": "application/json"},
            json={"text": texto, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.8,
                                     "speed": max(0.7, min(1.2, self.velocidade))}},
            timeout=60)
        resposta.raise_for_status()
        return resposta.content

    def _edge_mp3(self, texto: str) -> bytes:
        import edge_tts

        taxa = f"{int(round((self.velocidade * self.voz.velocidade - 1) * 100)):+d}%"

        async def gerar() -> bytes:
            comunicador = edge_tts.Communicate(texto, self.voz.base, rate=taxa)
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
                tocar(audio, formato, self._parar, self.ao_nivel)


def tocar(audio: bytes, formato: str, parar: threading.Event | None = None,
          ao_nivel=None) -> None:
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
                if ao_nivel is not None:
                    trecho = quadros[posicao:fim]
                    if len(trecho):
                        ao_nivel(min(1.0, max(abs(min(trecho)), abs(max(trecho))) / 22000))
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
        if ao_nivel is not None:
            ao_nivel(0.0)
        return
    for player in (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], ["mpv"],
                   ["aplay", "-q"], ["paplay"]):
        if shutil.which(player[0]):
            with tempfile.NamedTemporaryFile(suffix="." + formato, delete=False) as arquivo:
                arquivo.write(audio)
            subprocess.run([*player, arquivo.name], check=False)
            Path(arquivo.name).unlink(missing_ok=True)
            return
