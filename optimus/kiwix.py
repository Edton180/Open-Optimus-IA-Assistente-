"""Integração opcional com kiwix-serve para abrir bibliotecas ZIM locais.

O Optimus só inicia e encerra o processo que ele próprio criou. O servidor
fica restrito ao loopback e nunca é iniciado automaticamente.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path

from optimus import zim

HOST = "127.0.0.1"
PORT = 8767
_lock = threading.RLock()
_processo: subprocess.Popen | None = None
_arquivo_ativo: str | None = None


def _executavel() -> str | None:
    return shutil.which("kiwix-serve")


def _arquivo_seguro(nome: str) -> Path:
    if not isinstance(nome, str) or not nome or Path(nome).name != nome:
        raise ValueError("Selecione um arquivo ZIM válido da biblioteca.")
    if not nome.casefold().endswith(".zim"):
        raise ValueError("O arquivo selecionado precisa ter extensão .zim.")
    pasta = zim.pasta_biblioteca()
    alvo = pasta / nome
    if alvo.is_symlink() or not alvo.is_file() or alvo.resolve().parent != pasta.resolve():
        raise ValueError("O arquivo ZIM não existe na biblioteca gerenciada.")
    return alvo.resolve()


def estado() -> dict:
    """Retorna disponibilidade do executável e estado do processo gerenciado."""
    global _processo, _arquivo_ativo
    with _lock:
        executavel = _executavel()
        if _processo is not None and _processo.poll() is not None:
            _processo = None
            _arquivo_ativo = None
        ativo = _processo is not None
        return {
            "instalado": bool(executavel),
            "executavel_disponivel": bool(executavel),
            "executando": ativo,
            "arquivo": _arquivo_ativo if ativo else None,
            "url": f"http://{HOST}:{PORT}/" if ativo else None,
            "host": HOST,
            "porta": PORT,
        }


def iniciar(nome: str) -> dict:
    """Inicia kiwix-serve apenas para um ZIM gerenciado, sob demanda."""
    global _processo, _arquivo_ativo
    alvo = _arquivo_seguro(nome)
    with _lock:
        if _processo is not None and _processo.poll() is None:
            if _arquivo_ativo == alvo.name:
                return estado()
            raise RuntimeError("O leitor Kiwix já está aberto com outro arquivo. Feche-o antes.")
        _processo = None
        _arquivo_ativo = None
        executavel = _executavel()
        if not executavel:
            raise FileNotFoundError(
                "Kiwix não encontrado. Instale o kiwix-tools e tente novamente."
            )
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "shell": False,
            "close_fds": True,
        }
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        _processo = subprocess.Popen(
            [executavel, f"--address={HOST}", f"--port={PORT}", str(alvo)],
            **kwargs,
        )
        _arquivo_ativo = alvo.name
        time.sleep(0.35)
        if _processo.poll() is not None:
            _processo = None
            _arquivo_ativo = None
            raise RuntimeError(
                "O Kiwix encerrou durante a inicialização. Verifique se a porta "
                f"{PORT} está livre e se o arquivo ZIM é válido."
            )
        return estado()


def parar() -> dict:
    """Encerra exclusivamente o processo Kiwix iniciado por esta instância."""
    global _processo, _arquivo_ativo
    with _lock:
        processo = _processo
        if processo is not None and processo.poll() is None:
            processo.terminate()
            try:
                processo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=3)
        _processo = None
        _arquivo_ativo = None
        return estado()
