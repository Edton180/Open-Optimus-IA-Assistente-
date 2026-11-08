"""Caixa de ferramentas do Optimus.

Plugins: coloque arquivos .py na pasta plugins/ (dentro da pasta do Optimus) usando o
decorador `ferramenta`. Exemplo em docs/plugins.md.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from optimus.config import pasta_base
from optimus.tools import arquivos, casa, desktop, internet, memoria, sistema  # noqa: F401
from optimus.tools.base import Contexto, Ferramenta, ferramenta, registradas

log = logging.getLogger(__name__)
_PLUGINS_CARREGADOS = False


def carregar_plugins(pasta: Path | None = None) -> list[str]:
    global _PLUGINS_CARREGADOS
    pasta = pasta or (pasta_base() / "plugins")
    carregados = []
    if not pasta.is_dir():
        return carregados
    for arquivo in sorted(pasta.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"optimus_plugin_{arquivo.stem}",
                                                          arquivo)
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)  # type: ignore[union-attr]
            carregados.append(arquivo.stem)
        except Exception as erro:  # noqa: BLE001
            log.warning("Plugin %s não carregou: %s", arquivo.name, erro)
    _PLUGINS_CARREGADOS = True
    return carregados


def ferramentas_ativas(config) -> dict[str, Ferramenta]:
    grupos = config.dados.get("ferramentas", {})
    if grupos.get("plugins", True) and not _PLUGINS_CARREGADOS:
        carregar_plugins()
    ativas = {}
    sem_casa = not (config.get("casa", "url") and config.get("casa", "token"))
    for nome, item in registradas().items():
        if sem_casa and nome in ("casa_dispositivos", "casa_controlar"):
            continue
        if item.grupo in ("geral",) or grupos.get(item.grupo, True):
            ativas[nome] = item
    return ativas


__all__ = ["Contexto", "Ferramenta", "ferramenta", "ferramentas_ativas", "carregar_plugins"]
