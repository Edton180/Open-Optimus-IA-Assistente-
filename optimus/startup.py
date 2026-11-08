"""Iniciar o Optimus junto com o computador: optimus startup install|remove|status|restart|logs.

- Linux: serviço de usuário do systemd (~/.config/systemd/user/optimus.service).
- Windows: tarefa do Agendador de Tarefas que roda ao entrar no Windows (sem janela).
- Android (Termux): script em ~/.termux/boot/ (precisa do app Termux:Boot).

O serviço sobe a interface (optimus gui) e, se pedido, abre o navegador no núcleo (HUD),
onde fica a conversa ao vivo por voz. Nada aqui precisa de administrador.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from optimus.config import pasta_base

NOME = "optimus"
TAREFA_WINDOWS = "Open Optimus"


def plataforma() -> str:
    if "com.termux" in os.environ.get("PREFIX", "") or os.environ.get("TERMUX_VERSION"):
        return "termux"
    sistema = platform.system().lower()
    return "windows" if sistema == "windows" else "linux" if sistema == "linux" else sistema


def comando_optimus(abrir_navegador: bool) -> list[str]:
    comando = [sys.executable, "-m", "optimus", "gui"]
    if not abrir_navegador:
        comando.append("--sem-navegador")
    return comando


def arquivo_log() -> Path:
    pasta = pasta_base() / "registros"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / "inicio-automatico.log"


# ------------------------------------------------------------------ Linux (systemd)
def _unidade_systemd() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "systemd" / "user" / f"{NOME}.service"


def texto_unidade_systemd(comando: list[str]) -> str:
    executar = " ".join(f'"{p}"' if " " in p else p for p in comando)
    return (
        "[Unit]\n"
        "Description=Open Optimus (assistente de IA local)\n"
        "After=network-online.target sound.target\n\n"
        "[Service]\n"
        f"ExecStart={executar}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "Nice=5\n"
        "Environment=PYTHONUNBUFFERED=1\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True,
                          check=False)


# ------------------------------------------------------------------ Termux:Boot
def _script_termux() -> Path:
    return Path.home() / ".termux" / "boot" / "optimus.sh"


def texto_script_termux(comando: list[str]) -> str:
    return ("#!/data/data/com.termux/files/usr/bin/sh\n"
            "# Iniciado pelo app Termux:Boot quando o celular liga.\n"
            "termux-wake-lock\n"
            f"{' '.join(comando)} >> \"{arquivo_log()}\" 2>&1 &\n")


# ------------------------------------------------------------------ Windows
def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, check=False)


def comando_windows(comando: list[str]) -> str:
    # pythonw não abre janela preta; se não existir, usa o python normal.
    exe = Path(comando[0])
    sem_janela = exe.with_name("pythonw.exe")
    partes = [str(sem_janela if sem_janela.exists() else exe), *comando[1:]]
    return " ".join(f'"{p}"' if " " in p else p for p in partes)


# ------------------------------------------------------------------ ações
def instalar(abrir_navegador: bool = True) -> str:
    comando = comando_optimus(abrir_navegador)
    alvo = plataforma()
    if alvo == "linux":
        if not shutil.which("systemctl"):
            return _instalar_autostart_desktop(comando)
        unidade = _unidade_systemd()
        unidade.parent.mkdir(parents=True, exist_ok=True)
        unidade.write_text(texto_unidade_systemd(comando), encoding="utf-8")
        _systemctl("daemon-reload")
        resultado = _systemctl("enable", "--now", f"{NOME}.service")
        if resultado.returncode != 0:
            return (f"Criei {unidade}, mas o systemd recusou: {resultado.stderr.strip()}\n"
                    "Sem sessão do systemd (WSL, contêiner)? Use o autostart do desktop.")
        return (f"Pronto: o Optimus inicia com o computador (systemd, {unidade}).\n"
                "Para iniciar mesmo sem login: loginctl enable-linger $USER")
    if alvo == "windows":
        resultado = _schtasks("/Create", "/F", "/SC", "ONLOGON", "/RL", "LIMITED",
                              "/TN", TAREFA_WINDOWS, "/TR", comando_windows(comando))
        if resultado.returncode != 0:
            return f"O Agendador de Tarefas recusou: {resultado.stderr.strip() or resultado.stdout}"
        return f"Pronto: a tarefa '{TAREFA_WINDOWS}' inicia o Optimus quando você entra no Windows."
    if alvo == "termux":
        script = _script_termux()
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(texto_script_termux(comando_optimus(False)), encoding="utf-8")
        script.chmod(0o755)
        return (f"Pronto: criei {script}. Instale e abra uma vez o app Termux:Boot (F-Droid) "
                "para ele rodar quando o celular ligar.")
    return f"Início automático ainda não é suportado em {alvo}."


def _instalar_autostart_desktop(comando: list[str]) -> str:
    destino = Path.home() / ".config" / "autostart" / "optimus.desktop"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("[Desktop Entry]\nType=Application\nName=Open Optimus\n"
                       f"Exec={' '.join(comando)}\nX-GNOME-Autostart-enabled=true\n",
                       encoding="utf-8")
    return f"Pronto: {destino} inicia o Optimus quando você entra na área de trabalho."


def remover() -> str:
    alvo = plataforma()
    removidos = []
    if alvo == "linux":
        if shutil.which("systemctl"):
            _systemctl("disable", "--now", f"{NOME}.service")
        desktop = Path.home() / ".config" / "autostart" / "optimus.desktop"
        for arquivo in (_unidade_systemd(), desktop):
            if arquivo.exists():
                arquivo.unlink()
                removidos.append(str(arquivo))
        if shutil.which("systemctl"):
            _systemctl("daemon-reload")
    elif alvo == "windows":
        if _schtasks("/Delete", "/F", "/TN", TAREFA_WINDOWS).returncode == 0:
            removidos.append(TAREFA_WINDOWS)
    elif alvo == "termux" and _script_termux().exists():
        _script_termux().unlink()
        removidos.append(str(_script_termux()))
    return ("Removido: " + ", ".join(removidos)) if removidos else \
        "Não havia início automático instalado."


def status() -> str:
    alvo = plataforma()
    if alvo == "linux":
        if _unidade_systemd().exists() and shutil.which("systemctl"):
            ativo = _systemctl("is-active", f"{NOME}.service").stdout.strip()
            ligado = _systemctl("is-enabled", f"{NOME}.service").stdout.strip()
            return f"systemd: {ligado}, agora: {ativo} ({_unidade_systemd()})"
        desktop = Path.home() / ".config" / "autostart" / "optimus.desktop"
        return f"autostart do desktop: {desktop}" if desktop.exists() else "Não instalado."
    if alvo == "windows":
        resultado = _schtasks("/Query", "/TN", TAREFA_WINDOWS, "/FO", "LIST")
        return resultado.stdout.strip() if resultado.returncode == 0 else "Não instalado."
    if alvo == "termux":
        return f"Termux:Boot: {_script_termux()}" if _script_termux().exists() else "Não instalado."
    return "Não suportado neste sistema."


def reiniciar() -> str:
    alvo = plataforma()
    if alvo == "linux" and _unidade_systemd().exists():
        resultado = _systemctl("restart", f"{NOME}.service")
        return "Reiniciado." if resultado.returncode == 0 else resultado.stderr.strip()
    if alvo == "windows":
        _schtasks("/End", "/TN", TAREFA_WINDOWS)
        resultado = _schtasks("/Run", "/TN", TAREFA_WINDOWS)
        return "Reiniciado." if resultado.returncode == 0 else resultado.stderr.strip()
    return "Reinicie o Optimus manualmente (ou reinicie o aparelho)."


def logs(linhas: int = 60) -> str:
    if plataforma() == "linux" and _unidade_systemd().exists() and shutil.which("journalctl"):
        resultado = subprocess.run(["journalctl", "--user", "-u", f"{NOME}.service", "-n",
                                    str(linhas), "--no-pager"], capture_output=True, text=True,
                                   check=False)
        return resultado.stdout or resultado.stderr
    log = arquivo_log()
    if log.exists():
        return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-linhas:])
    return "Ainda não há registros."
