"""Controle do PC e de outros computadores da casa.

- Volume, brilho e mídia (tocar/pausar/próxima) no Windows, Linux e Android.
- Desempenho em tempo real: CPU, RAM, GPU, disco, rede, temperatura e bateria.
- Organizar pastas por tipo de arquivo ou por data.
- Outros PCs: ligar pela rede (Wake-on-LAN) e rodar comandos por SSH.
  Cadastre-os em [[computadores]] no config.toml (veja docs/controle.md).
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import psutil

from optimus.safety import BLOQUEADO, LIVRE, MODERADO, Avaliacao, risco_comando
from optimus.tools.base import ferramenta, no_android, numero, resolver, sistema, texto

# ---------------------------------------------------------------- teclas de mídia (Windows)
_VK = {"mudo": 0xAD, "baixar": 0xAE, "aumentar": 0xAF, "proxima": 0xB0, "anterior": 0xB1,
       "parar": 0xB2, "tocar": 0xB3, "pausar": 0xB3}


def _teclas_windows(codigo: int, vezes: int = 1) -> None:
    script = (
        "$a='[DllImport(\"user32.dll\")] public static extern void keybd_event(byte v, byte s, "
        "uint f, UIntPtr e);';$t=Add-Type -MemberDefinition $a -Name K -Namespace W -PassThru;"
        f"1..{max(1, vezes)} | % {{ $t::keybd_event({codigo},0,0,[UIntPtr]::Zero); "
        f"$t::keybd_event({codigo},0,2,[UIntPtr]::Zero) }}")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                   timeout=20, check=False)


def _rodar(comando: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(comando, capture_output=True, text=True, timeout=15, check=False)


# ---------------------------------------------------------------- volume
@ferramenta(
    "volume",
    "Controla o volume do PC: definir (0-100), aumentar, baixar, mudo, ou ver o atual.",
    {"acao": {"type": "string", "enum": ["definir", "aumentar", "baixar", "mudo", "ver"],
              "description": "O que fazer"},
     "valor": numero("Para definir: 0 a 100. Para aumentar/baixar: quanto (padrão 10)")},
    grupo="controle", obrigatorios=["acao"],
)
def volume(ctx, acao: str, valor: int = 0):
    acao = (acao or "ver").lower()
    valor = int(valor or (10 if acao in ("aumentar", "baixar") else 50))
    so = sistema()
    if so == "windows":
        if acao == "ver":
            return {"mensagem": "No Windows eu consigo ajustar, mas não ler o volume atual."}
        if acao == "mudo":
            _teclas_windows(_VK["mudo"])
        elif acao == "definir":
            _teclas_windows(_VK["baixar"], 50)
            _teclas_windows(_VK["aumentar"], round(max(0, min(100, valor)) / 2))
        else:
            _teclas_windows(_VK[acao], max(1, round(valor / 2)))
        return {"mensagem": f"Volume: {acao} {valor if acao != 'mudo' else ''}".strip()}
    if so == "android":
        if not shutil.which("termux-volume"):
            return {"erro": "Instale o Termux:API (pkg install termux-api)."}
        nivel = round(max(0, min(100, valor)) * 15 / 100)
        _rodar(["termux-volume", "music", str(0 if acao == "mudo" else nivel)])
        return {"mensagem": f"Volume ajustado ({acao})."}
    if shutil.which("pactl"):
        alvo = "@DEFAULT_SINK@"
        if acao == "ver":
            saida = _rodar(["pactl", "get-sink-volume", alvo]).stdout
            achado = re.search(r"(\d+)%", saida)
            return {"volume": int(achado.group(1)) if achado else None}
        if acao == "mudo":
            _rodar(["pactl", "set-sink-mute", alvo, "toggle"])
        else:
            quanto = {"definir": f"{valor}%", "aumentar": f"+{valor}%",
                      "baixar": f"-{valor}%"}[acao]
            _rodar(["pactl", "set-sink-mute", alvo, "0"])
            _rodar(["pactl", "set-sink-volume", alvo, quanto])
        return {"mensagem": f"Volume: {acao} {valor if acao != 'mudo' else ''}".strip()}
    if shutil.which("amixer"):
        if acao == "ver":
            achado = re.search(r"\[(\d+)%\]", _rodar(["amixer", "get", "Master"]).stdout)
            return {"volume": int(achado.group(1)) if achado else None}
        quanto = {"definir": f"{valor}%", "aumentar": f"{valor}%+", "baixar": f"{valor}%-",
                  "mudo": "toggle"}[acao]
        _rodar(["amixer", "-q", "sset", "Master", quanto])
        return {"mensagem": f"Volume: {acao}."}
    return {"erro": "Não achei controle de volume (instale pactl ou amixer)."}


# ---------------------------------------------------------------- brilho
@ferramenta(
    "brilho",
    "Ajusta o brilho da tela (0 a 100). Funciona em notebooks e monitores compatíveis.",
    {"valor": numero("Brilho de 0 a 100")}, grupo="controle",
)
def brilho(ctx, valor: int):
    valor = max(1, min(100, int(valor)))
    so = sistema()
    if so == "windows":
        script = ("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                  f".WmiSetBrightness(1,{valor})")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, text=True, timeout=20, check=False)
        if r.returncode != 0:
            return {"erro": "Este monitor não aceita ajuste de brilho pelo Windows."}
        return {"mensagem": f"Brilho em {valor}%."}
    if so == "android":
        if shutil.which("termux-brightness"):
            _rodar(["termux-brightness", str(round(valor * 255 / 100))])
            return {"mensagem": f"Brilho em {valor}%."}
        return {"erro": "Instale o Termux:API (pkg install termux-api)."}
    if shutil.which("brightnessctl"):
        _rodar(["brightnessctl", "set", f"{valor}%"])
        return {"mensagem": f"Brilho em {valor}%."}
    if shutil.which("xrandr"):
        saidas = re.findall(r"^(\S+) connected", _rodar(["xrandr"]).stdout, re.M)
        for saida in saidas:
            _rodar(["xrandr", "--output", saida, "--brightness", str(max(0.2, valor / 100))])
        if saidas:
            return {"mensagem": f"Brilho em {valor}% (ajuste por software)."}
    return {"erro": "Não achei como ajustar o brilho (instale brightnessctl)."}


# ---------------------------------------------------------------- mídia
@ferramenta(
    "midia",
    "Controla o que está tocando no PC (Spotify, YouTube, player): tocar, pausar, proxima, "
    "anterior, parar.",
    {"acao": {"type": "string", "enum": ["tocar", "pausar", "proxima", "anterior", "parar"],
              "description": "O que fazer"}},
    grupo="controle",
)
def midia(ctx, acao: str):
    acao = (acao or "tocar").lower()
    so = sistema()
    if so == "windows":
        _teclas_windows(_VK.get(acao, _VK["tocar"]))
        return {"mensagem": f"Mídia: {acao}."}
    if so == "android":
        return {"erro": "No Android, controle a mídia pelo próprio celular."}
    if shutil.which("playerctl"):
        comando = {"tocar": "play-pause", "pausar": "pause", "proxima": "next",
                   "anterior": "previous", "parar": "stop"}[acao]
        r = _rodar(["playerctl", comando])
        if r.returncode != 0:
            return {"erro": "Nenhum player aberto."}
        return {"mensagem": f"Mídia: {acao}."}
    return {"erro": "Instale o playerctl para controlar a mídia no Linux."}


# ---------------------------------------------------------------- desempenho
def _gpu() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        return []
    saida = _rodar(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,"
                    "temperature.gpu", "--format=csv,noheader,nounits"]).stdout
    placas = []
    for linha in saida.strip().splitlines():
        partes = [p.strip() for p in linha.split(",")]
        if len(partes) == 5:
            placas.append({"nome": partes[0], "uso": f"{partes[1]}%",
                           "vram": f"{partes[2]}/{partes[3]} MB", "temperatura": f"{partes[4]}°C"})
    return placas


@ferramenta(
    "desempenho",
    "Mostra o uso do PC agora: CPU (por núcleo), RAM, GPU, disco, rede (velocidade), "
    "temperatura e bateria.",
    grupo="geral",
)
def desempenho(ctx):
    rede_antes = psutil.net_io_counters()
    cpu = psutil.cpu_percent(interval=1, percpu=True)
    rede_depois = psutil.net_io_counters()
    memoria = psutil.virtual_memory()
    dados = {
        "cpu_total": f"{sum(cpu) / max(1, len(cpu)):.0f}%",
        "cpu_por_nucleo": [f"{c:.0f}%" for c in cpu],
        "ram": f"{memoria.percent}% ({memoria.used / 1024**3:.1f} de "
               f"{memoria.total / 1024**3:.1f} GB)",
        "rede_download": f"{(rede_depois.bytes_recv - rede_antes.bytes_recv) / 1024:.0f} KB/s",
        "rede_upload": f"{(rede_depois.bytes_sent - rede_antes.bytes_sent) / 1024:.0f} KB/s",
        "gpu": _gpu() or "sem GPU NVIDIA detectada",
    }
    try:
        disco = psutil.disk_usage(str(Path.home()))
        dados["disco"] = f"{disco.percent}% usado ({disco.free / 1024**3:.0f} GB livres)"
    except OSError:
        pass
    temperaturas = getattr(psutil, "sensors_temperatures", lambda: {})() or {}
    for nome, sensores in temperaturas.items():
        if sensores:
            dados["temperatura_cpu"] = f"{sensores[0].current:.0f}°C ({nome})"
            break
    bateria = getattr(psutil, "sensors_battery", lambda: None)()
    if bateria:
        dados["bateria"] = f"{bateria.percent:.0f}%" + (" carregando" if bateria.power_plugged
                                                        else "")
    return dados


# ---------------------------------------------------------------- organizar pastas
CATEGORIAS = {
    "Imagens": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".raw"},
    "Vídeos": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv"},
    "Músicas": {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"},
    "Documentos": {".pdf", ".doc", ".docx", ".odt", ".txt", ".rtf", ".md", ".epub"},
    "Planilhas": {".xls", ".xlsx", ".ods", ".csv"},
    "Apresentações": {".ppt", ".pptx", ".odp", ".key"},
    "Compactados": {".zip", ".rar", ".7z", ".tar", ".gz", ".xz", ".bz2"},
    "Programas": {".exe", ".msi", ".deb", ".rpm", ".appimage", ".apk", ".dmg", ".sh", ".bat"},
    "Código": {".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".c", ".cpp", ".go",
               ".rs", ".php", ".sql", ".yml", ".yaml", ".toml", ".ipynb"},
}


def categoria(nome: str) -> str:
    extensao = Path(nome).suffix.lower()
    for pasta, extensoes in CATEGORIAS.items():
        if extensao in extensoes:
            return pasta
    return "Outros"


@ferramenta(
    "organizar_pasta",
    "Organiza os arquivos soltos de uma pasta em subpastas por tipo (Imagens, Vídeos, "
    "Documentos...) ou por mês. Com simular=true só mostra o plano, sem mover nada.",
    {"pasta": texto("Pasta, ex.: ~/Downloads"),
     "modo": {"type": "string", "enum": ["tipo", "data"], "description": "Como agrupar"},
     "simular": {"type": "boolean", "description": "Só mostrar o plano (padrão true)"}},
    grupo="arquivos", obrigatorios=["pasta"],
    risco=lambda a, c: Avaliacao(LIVRE if a.get("simular", True) else MODERADO,
                                 f"organizar a pasta {a.get('pasta')}"),
)
def organizar_pasta(ctx, pasta: str, modo: str = "tipo", simular: bool = True):
    base = resolver(ctx, pasta)
    plano: dict[str, list[str]] = {}
    for item in sorted(base.iterdir()):
        if not item.is_file() or item.name.startswith("."):
            continue
        if modo == "data":
            grupo = time.strftime("%Y-%m", time.localtime(item.stat().st_mtime))
        else:
            grupo = categoria(item.name)
        plano.setdefault(grupo, []).append(item.name)
    if simular:
        return {"pasta": str(base), "plano": {k: len(v) for k, v in plano.items()},
                "exemplos": {k: v[:5] for k, v in plano.items()},
                "mensagem": "Plano pronto. Peça para executar com simular=false."}
    movidos = 0
    for grupo, nomes in plano.items():
        destino = base / grupo
        destino.mkdir(exist_ok=True)
        for nome in nomes:
            alvo = destino / nome
            contador = 1
            while alvo.exists():
                alvo = destino / f"{Path(nome).stem} ({contador}){Path(nome).suffix}"
                contador += 1
            shutil.move(str(base / nome), str(alvo))
            movidos += 1
    return {"mensagem": f"{movidos} arquivos organizados em {len(plano)} pastas.",
            "pastas": {k: len(v) for k, v in plano.items()}}


# ---------------------------------------------------------------- outros computadores
def _computadores(ctx) -> list[dict]:
    return list(ctx.config.dados.get("computadores") or [])


def _achar_pc(ctx, nome: str) -> dict | None:
    alvo = (nome or "").strip().lower()
    for pc in _computadores(ctx):
        if alvo in (str(pc.get("nome", "")).lower(), str(pc.get("host", "")).lower()):
            return pc
    return None


def pacote_wol(mac: str) -> bytes:
    """Pacote mágico do Wake-on-LAN: 6 bytes FF + o MAC repetido 16 vezes."""
    limpo = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(limpo) != 12:
        raise ValueError(f"Endereço MAC inválido: {mac}")
    return b"\xff" * 6 + bytes.fromhex(limpo) * 16


def _porta_aberta(host: str, porta: int, espera: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, porta), timeout=espera):
            return True
    except OSError:
        return False


@ferramenta(
    "pc_listar",
    "Lista os outros computadores cadastrados e se estão ligados.", grupo="controle",
)
def pc_listar(ctx):
    itens = []
    for pc in _computadores(ctx):
        host = pc.get("host", "")
        ligado = bool(host) and _porta_aberta(host, int(pc.get("porta") or 22))
        itens.append({"nome": pc.get("nome"), "host": host, "ligado": ligado,
                      "liga_pela_rede": bool(pc.get("mac"))})
    if not itens:
        return {"mensagem": "Nenhum computador cadastrado. Adicione em [[computadores]] no "
                            "config.toml (nome, host, usuario, mac)."}
    return {"total": len(itens), "itens": itens}


@ferramenta(
    "pc_ligar",
    "Liga outro computador da casa pela rede (Wake-on-LAN). O PC precisa ter o recurso "
    "ligado na BIOS e estar no cabo ou Wi-Fi compatível.",
    {"nome": texto("Nome do computador cadastrado")},
    grupo="controle", risco=lambda a, c: Avaliacao(MODERADO, f"ligar o PC {a.get('nome')}"),
)
def pc_ligar(ctx, nome: str):
    pc = _achar_pc(ctx, nome)
    if not pc or not pc.get("mac"):
        return {"erro": f"Não achei '{nome}' com endereço MAC cadastrado."}
    pacote = pacote_wol(pc["mac"])
    destino = pc.get("broadcast") or "255.255.255.255"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for porta in (9, 7):
            s.sendto(pacote, (destino, porta))
    return {"mensagem": f"Sinal para ligar enviado a {pc.get('nome')}. Leva uns segundos."}


def _risco_pc_comando(args, ctx) -> Avaliacao:
    nivel = max(MODERADO, risco_comando(args.get("comando", "")))
    return Avaliacao(nivel, f"rodar em {args.get('nome')}: {args.get('comando')}")


@ferramenta(
    "pc_comando",
    "Roda um comando em outro computador da casa por SSH (precisa de chave SSH configurada) "
    "e devolve a saída. Serve para ver o estado, abrir programas, desligar, atualizar...",
    {"nome": texto("Nome do computador cadastrado"), "comando": texto("Comando a rodar lá")},
    grupo="controle", risco=_risco_pc_comando,
)
def pc_comando(ctx, nome: str, comando: str):
    if risco_comando(comando) >= BLOQUEADO:
        return {"erro": "Comando bloqueado por segurança."}
    pc = _achar_pc(ctx, nome)
    if not pc or not pc.get("host"):
        return {"erro": f"Não achei o computador '{nome}'. Use pc_listar."}
    if not shutil.which("ssh"):
        return {"erro": "O cliente SSH não está instalado neste PC."}
    destino = f"{pc['usuario']}@{pc['host']}" if pc.get("usuario") else pc["host"]
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                            "-p", str(pc.get("porta") or 22), destino, comando],
                           capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"erro": "O computador não respondeu a tempo."}
    return {"codigo": r.returncode, "saida": r.stdout[-8000:], "erros": r.stderr[-2000:]}


__all__ = ["pacote_wol", "categoria", "no_android"]
