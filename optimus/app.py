"""Junta as peças: configuração, hardware, banco, motor, agente e lembretes."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import psutil

from optimus import config as cfg
from optimus import hardware
from optimus.agent import Agente
from optimus.banco import Banco
from optimus.engine import criar_motor
from optimus.safety import Auditoria
from optimus.tools import ferramentas_ativas

log = logging.getLogger(__name__)


class Optimus:
    def __init__(self, config: cfg.Config | None = None):
        self.config = config or cfg.carregar()
        self.hardware = hardware.detectar()
        self.perfil = hardware.escolher_perfil(self.hardware)
        from optimus.modelos import verificar_upgrade

        self.aviso_modelo = verificar_upgrade(self.config, self.hardware, self.perfil)
        base = cfg.pasta_base()
        self.banco = Banco(base / "optimus.db")
        self.auditoria = Auditoria(base / "registros" / "acoes.jsonl")
        self.motor = criar_motor(self.config)
        self._lembretes: threading.Thread | None = None
        if self.config.get("recursos", "prioridade_baixa", True):
            _baixar_prioridade()

    def recarregar(self) -> None:
        self.config = cfg.carregar(self.config.caminho)
        self.motor = criar_motor(self.config)

    def criar_agente(self, confirmar=None, ao_evento=None) -> Agente:
        return Agente(config=self.config, motor=self.motor, banco=self.banco, perfil=self.perfil,
                      confirmar=confirmar, ao_evento=ao_evento, auditoria=self.auditoria,
                      ferramentas=ferramentas_ativas(self.config))

    def modelo_atual(self) -> str:
        from optimus.engine.demo import MotorDemo

        if isinstance(self.motor, MotorDemo):
            return "modo demonstração (sem modelo)"
        return self.config.get("motor", "modelo") or self.perfil.modelo

    def iniciar_lembretes(self, avisar: Callable[[dict[str, Any]], None]) -> None:
        if self._lembretes and self._lembretes.is_alive():
            return

        def ciclo():
            while True:
                try:
                    for lembrete in self.banco.lembretes_vencidos():
                        avisar(lembrete)
                        self.banco.concluir_lembrete(lembrete)
                except Exception as erro:  # noqa: BLE001
                    log.warning("Falha nos lembretes: %s", erro)
                time.sleep(15)

        self._lembretes = threading.Thread(target=ciclo, daemon=True, name="lembretes")
        self._lembretes.start()


def _baixar_prioridade() -> None:
    """Deixa o Optimus com prioridade baixa para o PC continuar fluido."""
    try:
        processo = psutil.Process()
        if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
            processo.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            processo.nice(5)
    except (psutil.Error, OSError):
        pass
