"""Gerenciamento seguro do Cloudflare Quick Tunnel.

O modo Quick Tunnel não exige conta, token, zona DNS ou domínio próprio. Para
hostnames permanentes e DNS gerenciado, é necessária uma integração separada com
a API Cloudflare e credenciais explicitamente autorizadas pelo usuário.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

import httpx

from optimus.config import pasta_base

log = logging.getLogger(__name__)
_RELEASE_API = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"
_LOCK = threading.RLock()
_PROCESS: subprocess.Popen | None = None
_URL = ""
_ERROR = ""
_READER: threading.Thread | None = None
_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)


class TunnelError(RuntimeError):
    """Erro operacional do Cloudflare Tunnel."""


def _asset_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        if machine in ("amd64", "x86_64"):
            return "cloudflared-windows-amd64.exe"
        if machine in ("arm64", "aarch64"):
            return "cloudflared-windows-arm64.exe"
    elif system == "linux":
        if machine in ("amd64", "x86_64"):
            return "cloudflared-linux-amd64"
        if machine in ("arm64", "aarch64"):
            return "cloudflared-linux-arm64"
        if machine.startswith("armv7"):
            return "cloudflared-linux-arm"
    raise TunnelError(f"Arquitetura não suportada pelo instalador automático: {system}/{machine}.")


def _binario_local() -> Path:
    nome = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    return pasta_base() / "bin" / nome


def localizar() -> str | None:
    """Prefere a cópia gerenciada pelo Optimus e depois procura no PATH."""
    local = _binario_local()
    if local.is_file():
        return str(local)
    return shutil.which("cloudflared")


def garantir_instalado(timeout: float = 45.0) -> str:
    """Instala a versão oficial mais recente em diretório privado do Optimus.

    A instalação só é aceita quando o GitHub publica digest SHA-256 para o asset.
    """
    existente = localizar()
    if existente:
        return existente
    asset_name = _asset_name()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Open-Optimus"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            release = client.get(_RELEASE_API)
            release.raise_for_status()
            dados = release.json()
            asset = next((a for a in dados.get("assets", []) if a.get("name") == asset_name), None)
            if asset is None:
                raise TunnelError(f"Versão oficial não oferece o binário {asset_name}.")
            digest = str(asset.get("digest") or "")
            if not digest.startswith("sha256:"):
                raise TunnelError("O GitHub não forneceu SHA-256 verificável para o binário; "
                                  "instalação automática cancelada por segurança.")
            download = client.get(asset["browser_download_url"])
            download.raise_for_status()
            payload = download.content
        calculado = hashlib.sha256(payload).hexdigest()
        if not __import__("hmac").compare_digest(calculado, digest.removeprefix("sha256:")):
            raise TunnelError("A verificação SHA-256 do cloudflared falhou.")
        destino = _binario_local()
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(destino.suffix + ".part")
        temporario.write_bytes(payload)
        if os.name != "nt":
            temporario.chmod(0o700)
        temporario.replace(destino)
        return str(destino)
    except TunnelError:
        raise
    except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
        raise TunnelError(f"Não foi possível instalar cloudflared com segurança: {exc}") from exc


def estado() -> dict[str, str | bool]:
    with _LOCK:
        processo = _PROCESS
        vivo = processo is not None and processo.poll() is None
        if processo is not None and not vivo and not _ERROR:
            return {"ligado": False, "iniciando": False, "url": "",
                    "erro": f"cloudflared encerrou com código {processo.returncode}."}
        return {"ligado": bool(vivo and _URL), "iniciando": bool(vivo and not _URL),
                "url": _URL if vivo else "", "erro": _ERROR}


def iniciar(porta: int, senha: str, *, instalador: Callable[[], str] = garantir_instalado,
            espera: float = 20.0) -> dict[str, str | bool]:
    """Inicia/reutiliza um Quick Tunnel apontando somente para localhost."""
    global _PROCESS, _URL, _ERROR, _READER
    if len(senha or "") < 12:
        return {"erro": "Acesso externo exige senha com pelo menos 12 caracteres."}
    if not 1 <= int(porta) <= 65535:
        return {"erro": "Porta local inválida."}
    try:
        executavel = instalador()
    except Exception as exc:  # erro apresentado no painel
        with _LOCK:
            _ERROR = str(exc)
        return {"ligado": False, "url": "", "erro": str(exc)}
    with _LOCK:
        if _PROCESS is not None and _PROCESS.poll() is None:
            return estado()
        _URL = ""
        _ERROR = ""
        try:
            processo = subprocess.Popen(
                [executavel, "tunnel", "--no-autoupdate", "--url",
                 f"http://127.0.0.1:{int(porta)}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                stdin=subprocess.DEVNULL)
        except OSError as exc:
            _ERROR = f"Não foi possível iniciar o Cloudflare Tunnel: {exc}"
            return {"ligado": False, "url": "", "erro": _ERROR}
        _PROCESS = processo

    def ler_saida() -> None:
        global _URL, _ERROR
        try:
            for linha in processo.stdout or ():
                # Não registrar a saída bruta: pode conter identificadores operacionais.
                match = _URL_RE.search(linha)
                if match:
                    with _LOCK:
                        _URL = match.group(0)
        except (OSError, ValueError) as exc:
            log.debug("Leitura do processo cloudflared encerrada: %s", exc)

    _READER = threading.Thread(target=ler_saida, daemon=True, name="optimus-cloudflared")
    _READER.start()
    limite = time.monotonic() + max(1.0, espera)
    while time.monotonic() < limite:
        atual = estado()
        if atual.get("url") or atual.get("erro"):
            return atual
        if processo.poll() is not None:
            with _LOCK:
                _ERROR = f"cloudflared encerrou com código {processo.returncode}."
            return estado()
        time.sleep(0.1)
    return estado()


def parar() -> None:
    global _PROCESS, _URL, _ERROR
    with _LOCK:
        processo = _PROCESS
        _PROCESS = None
        _URL = ""
        _ERROR = ""
    if processo is not None and processo.poll() is None:
        processo.terminate()
        try:
            processo.wait(timeout=5)
        except subprocess.TimeoutExpired:
            processo.kill()
            processo.wait(timeout=2)
