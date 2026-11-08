"""Detecção de hardware e escolha automática do modelo.

O Optimus olha CPU, RAM e placa de vídeo e escolhe um perfil. Cada perfil define o
modelo principal, um modelo rápido para respostas curtas (voz), o tamanho do contexto,
quantas threads usar e qual modelo de reconhecimento de voz cabe na máquina.

A ideia de mapear memória disponível para tamanho de modelo vem do OpenJarvis
(Apache 2.0). Aqui a tabela vai de PCs bem fracos (2 a 4 GB de RAM) até placas de 24 GB
ou mais, e usa modelos MoE quando o PC tem muita RAM mas não tem placa de vídeo,
porque eles rodam rápido na CPU.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field

import psutil


@dataclass
class Placa:
    fabricante: str  # nvidia | amd | intel | apple | desconhecido
    nome: str
    vram_gb: float = 0.0
    quantidade: int = 1


@dataclass
class Hardware:
    sistema: str
    versao_sistema: str
    arquitetura: str
    cpu: str
    nucleos_fisicos: int
    nucleos_logicos: int
    ram_total_gb: float
    ram_livre_gb: float
    placa: Placa | None = None
    placas: list[Placa] = field(default_factory=list)

    def para_dict(self) -> dict:
        return asdict(self)


@dataclass
class Perfil:
    nome: str
    descricao: str
    modelo: str
    alternativas: list[str]
    modelo_rapido: str
    contexto: int
    threads: int
    usa_gpu: bool
    modelo_stt: str
    memoria_util_gb: float

    def para_dict(self) -> dict:
        return asdict(self)


def _rodar(comando: list[str], tempo: float = 6.0) -> str:
    if not shutil.which(comando[0]):
        return ""
    try:
        resultado = subprocess.run(
            comando, capture_output=True, text=True, timeout=tempo, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return resultado.stdout.strip() if resultado.returncode == 0 else ""


def _placas_nvidia() -> list[Placa]:
    saida = _rodar(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
    )
    placas = []
    for linha in saida.splitlines():
        partes = [p.strip() for p in linha.split(",")]
        if len(partes) >= 2:
            try:
                vram = round(float(partes[1]) / 1024, 1)
            except ValueError:
                vram = 0.0
            placas.append(Placa("nvidia", partes[0], vram))
    return placas


def _placas_amd() -> list[Placa]:
    saida = _rodar(["rocm-smi", "--showmeminfo", "vram", "--csv"])
    placas = []
    for linha in saida.splitlines()[1:]:
        partes = [p.strip() for p in linha.split(",")]
        if len(partes) >= 2 and partes[1].isdigit():
            placas.append(Placa("amd", "AMD Radeon", round(int(partes[1]) / 1024**3, 1)))
    return placas


def _placas_windows() -> list[Placa]:
    """Placas no Windows pelo registro de vídeo (pega VRAM acima de 4 GB corretamente)."""
    script = (
        "Get-ItemProperty 'HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\"
        "{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' -ErrorAction SilentlyContinue | "
        "ForEach-Object { \"$($_.DriverDesc)|$($_.'HardwareInformation.qwMemorySize')\" }"
    )
    saida = _rodar(["powershell", "-NoProfile", "-Command", script], tempo=10)
    placas = []
    for linha in saida.splitlines():
        if "|" not in linha:
            continue
        nome, memoria = linha.split("|", 1)
        if not nome.strip():
            continue
        try:
            vram = round(int(memoria) / 1024**3, 1) if memoria.strip() else 0.0
        except ValueError:
            vram = 0.0
        baixo = nome.lower()
        fabricante = (
            "nvidia" if "nvidia" in baixo else
            "amd" if ("amd" in baixo or "radeon" in baixo) else
            "intel" if "intel" in baixo else "desconhecido"
        )
        placas.append(Placa(fabricante, nome.strip(), vram))
    return placas


def _placas_linux_lspci() -> list[Placa]:
    saida = _rodar(["lspci"])
    placas = []
    for linha in saida.splitlines():
        if "VGA" in linha or "3D controller" in linha:
            nome = linha.split(":", 2)[-1].strip()
            baixo = nome.lower()
            fabricante = (
                "nvidia" if "nvidia" in baixo else
                "amd" if ("amd" in baixo or "ati" in baixo) else
                "intel" if "intel" in baixo else "desconhecido"
            )
            placas.append(Placa(fabricante, nome, 0.0))
    return placas


def _nome_cpu() -> str:
    sistema = platform.system()
    if sistema == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as arquivo:
                for linha in arquivo:
                    if linha.startswith("model name"):
                        return linha.split(":", 1)[1].strip()
        except OSError:
            pass
    if sistema == "Windows":
        nome = _rodar(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"]
        )
        if nome:
            return nome.splitlines()[0].strip()
    if sistema == "Darwin":
        nome = _rodar(["sysctl", "-n", "machdep.cpu.brand_string"])
        if nome:
            return nome
    return platform.processor() or "CPU desconhecida"


def detectar() -> Hardware:
    memoria = psutil.virtual_memory()
    placas = _placas_nvidia() or _placas_amd()
    if not placas:
        if platform.system() == "Windows":
            placas = _placas_windows()
        elif platform.system() == "Linux":
            placas = _placas_linux_lspci()
        elif platform.system() == "Darwin" and platform.machine() == "arm64":
            placas = [Placa("apple", "Apple Silicon", round(memoria.total / 1024**3 * 0.7, 1))]
    dedicadas = [p for p in placas if p.fabricante in ("nvidia", "amd", "apple") and p.vram_gb]
    principal = max(dedicadas, key=lambda p: p.vram_gb) if dedicadas else None
    return Hardware(
        sistema=platform.system(),
        versao_sistema=platform.release(),
        arquitetura=platform.machine(),
        cpu=_nome_cpu(),
        nucleos_fisicos=psutil.cpu_count(logical=False) or os.cpu_count() or 1,
        nucleos_logicos=psutil.cpu_count(logical=True) or os.cpu_count() or 1,
        ram_total_gb=round(memoria.total / 1024**3, 1),
        ram_livre_gb=round(memoria.available / 1024**3, 1),
        placa=principal,
        placas=placas,
    )


# (memória útil máxima em GB, perfil, descrição, modelo, alternativas, contexto, stt)
_TABELA = [
    (3.0, "mínimo", "PC bem modesto (até 4 GB de RAM livres)",
     "qwen3.5:0.8b", ["qwen3:0.6b", "llama3.2:1b"], 2048, "tiny"),
    (6.0, "leve", "Notebook ou PC de entrada",
     "qwen3.5:2b", ["qwen3:1.7b", "llama3.2:3b"], 4096, "base"),
    (10.0, "médio", "PC intermediário",
     "qwen3.5:4b", ["qwen3:4b", "llama3.2:3b"], 8192, "small"),
    (20.0, "forte", "PC forte ou placa de vídeo de 8 a 16 GB",
     "qwen3.5:9b", ["qwen3:8b", "llama3.1:8b"], 16384, "small"),
    (40.0, "ultra", "Placa de vídeo de 24 GB ou mais",
     "qwen3.5:27b", ["qwen3:32b", "qwen3:14b"], 32768, "large-v3-turbo"),
]
_MAXIMO = ("máximo", "Estação de trabalho com várias placas ou muita VRAM",
           "qwen3.5:35b-a3b", ["qwen3.5:27b", "qwen3:30b"], 32768, "large-v3-turbo")


def memoria_util_gb(hw: Hardware) -> tuple[float, bool]:
    """Quanta memória sobra para o modelo, e se ela é de placa de vídeo."""
    if hw.placa and hw.placa.vram_gb >= 4:
        return round(hw.placa.vram_gb * max(hw.placa.quantidade, 1) * 0.9, 1), True
    reserva = 2.0 if hw.ram_total_gb <= 8 else 4.0
    pela_total = (hw.ram_total_gb - reserva) * 0.8
    # Se o sistema já está usando muita RAM, não adianta escolher um modelo que não cabe.
    pela_livre = hw.ram_livre_gb * 0.85
    return round(max(0.5, min(pela_total, pela_livre + 1.0)), 1), False


def escolher_perfil(hw: Hardware) -> Perfil:
    memoria, usa_gpu = memoria_util_gb(hw)
    escolhido = _MAXIMO
    for limite, *resto in _TABELA:
        if memoria <= limite:
            escolhido = tuple(resto)
            break
    nome, descricao, modelo, alternativas, contexto, stt = escolhido

    # Sem placa de vídeo, mas com muita RAM: o modelo MoE (3B ativos) responde rápido na CPU
    # e é bem mais inteligente que um modelo denso do mesmo custo.
    if not usa_gpu and memoria >= 22:
        nome, descricao = "forte (CPU)", "Muita RAM e sem placa de vídeo: modelo MoE rápido na CPU"
        modelo, alternativas, contexto = "qwen3.5:35b-a3b", ["qwen3:30b", "qwen3.5:9b"], 16384

    # Para conversar por voz, um modelo pequeno responde quase na hora.
    rapido = "qwen3.5:2b" if nome not in ("mínimo", "leve") else modelo

    threads = hw.nucleos_fisicos
    if nome in ("mínimo", "leve") and threads > 2:
        threads -= 1  # deixa um núcleo para o sistema não travar
    return Perfil(
        nome=nome,
        descricao=descricao,
        modelo=modelo,
        alternativas=list(alternativas),
        modelo_rapido=rapido,
        contexto=contexto,
        threads=max(1, threads),
        usa_gpu=usa_gpu,
        modelo_stt=stt,
        memoria_util_gb=memoria,
    )


def resumo(hw: Hardware, perfil: Perfil) -> str:
    placa = (
        f"{hw.placa.nome} ({hw.placa.vram_gb} GB)" if hw.placa else "nenhuma placa dedicada"
    )
    return (
        f"Sistema: {hw.sistema} {hw.versao_sistema} ({hw.arquitetura})\n"
        f"CPU: {hw.cpu} ({hw.nucleos_fisicos} núcleos, {hw.nucleos_logicos} threads)\n"
        f"RAM: {hw.ram_total_gb} GB (livre: {hw.ram_livre_gb} GB)\n"
        f"Placa de vídeo: {placa}\n"
        f"Perfil: {perfil.nome} ({perfil.descricao})\n"
        f"Modelo principal: {perfil.modelo} (alternativas: {', '.join(perfil.alternativas)})\n"
        f"Modelo rápido (voz): {perfil.modelo_rapido}\n"
        f"Contexto: {perfil.contexto} tokens, threads: {perfil.threads}, "
        f"GPU: {'sim' if perfil.usa_gpu else 'não'}\n"
        f"Reconhecimento de voz: whisper {perfil.modelo_stt}"
    )
