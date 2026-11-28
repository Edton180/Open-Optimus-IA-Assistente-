"""Descobre se um pacote Python opcional (motor de IA) está instalado para este Optimus.

Dois cuidados que o `importlib.util.find_spec` sozinho não tem:
- O Python guarda a lista de arquivos de cada pasta. Um pacote instalado com o Optimus já
  aberto (em outro terminal, ou pela aba Modelos) não aparecia até reiniciar. Aqui a lista
  é renovada a cada consulta.
- `pip install --user` cria a pasta de pacotes do usuário depois que o Optimus abriu; ela
  não estava no `sys.path`. Aqui ela entra quando passa a existir.

`comando_pip` monta o comando com o Python que roda o Optimus. Um `pip install` solto pode
instalar em outro Python do PC, e aí o Optimus não enxerga o motor.
"""

from __future__ import annotations

import importlib
import importlib.util
import site
import sys
from pathlib import Path


def _pastas_novas() -> None:
    try:
        pastas = [site.getusersitepackages()]
    except Exception:  # noqa: BLE001 - Python embutido sem `site` completo
        pastas = []
    for pasta in pastas:
        if pasta and pasta not in sys.path and Path(pasta).is_dir():
            site.addsitedir(pasta)


def modulo_instalado(modulo: str) -> bool:
    importlib.invalidate_caches()
    _pastas_novas()
    try:
        return importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        return False


def python_do_optimus() -> str:
    return sys.executable or "python"


def comando_pip(pacote: str) -> str:
    """Ex.: "C:\\...\\python.exe" -m pip install "sherpa-onnx<2"."""
    py = python_do_optimus()
    if " " in py:
        py = f'"{py}"'
    alvo = f'"{pacote}"' if any(c in pacote for c in "<>= ") else pacote
    return f"{py} -m pip install {alvo}"
