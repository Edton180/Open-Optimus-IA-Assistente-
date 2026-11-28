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
        from optimus.smart_home.registry import RegistroDispositivos
        self.registro_casa = RegistroDispositivos(base / "casa" / "dispositivos.json")
        self.banco = Banco(base / "optimus.db")
        self._iniciar_indexacao_conhecimento(base)
        self.auditoria = Auditoria(base / "registros" / "acoes.jsonl")
        self.motor = criar_motor(self.config)
        self._lembretes: threading.Thread | None = None
        self._copiados: threading.Thread | None = None
        self.aviso_atualizacao: dict | None = None
        if self.config.get("atualizacao", "ao_iniciar", False):
            threading.Thread(target=self._verificar_atualizacao, daemon=True,
                             name="atualizacao").start()
        if self.config.get("recursos", "prioridade_baixa", True):
            _baixar_prioridade()

    def _iniciar_indexacao_conhecimento(self, base) -> None:
        """Indexa a base embutida em segundo plano para não atrasar a abertura do servidor."""
        threading.Thread(target=self._indexar_conhecimento, args=(base,), daemon=True,
                         name="indexacao-conhecimento").start()

    def _indexar_conhecimento(self, base) -> None:
        """Indexa a base de conhecimento embutida no banco (idempotente, só o que mudou).

        Falha aqui nunca deve travar a abertura do Optimus, então é toda protegida.
        """
        try:
            from optimus import conhecimento

            conhecimento.indexar_embutido(self.banco, estado_arq=base / "conhecimento.json")
        except Exception:
            pass

    def _verificar_atualizacao(self) -> None:
        from optimus import autoatualizar

        self.aviso_atualizacao = autoatualizar.automatico(self.config)

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

    def _verificar_avisos(self, avisar: Callable[[dict[str, Any]], None]) -> None:
        """Uma passada: lembretes vencidos e timers que chegaram ao fim."""
        for lembrete in self.banco.lembretes_vencidos():
            avisar(lembrete)
            self.banco.concluir_lembrete(lembrete)
        for timer in self.banco.timers_vencidos():
            nome = (timer.get("nome") or "Timer").strip() or "Timer"
            avisar({"tipo": "timer", "id": timer["id"], "nome": nome,
                    "texto": f"Timer '{nome}' terminou."})
            self.banco.marcar_timer_tocado(timer["id"])

    def iniciar_lembretes(self, avisar: Callable[[dict[str, Any]], None]) -> None:
        if self._lembretes and self._lembretes.is_alive():
            return

        def ciclo():
            while True:
                try:
                    self._verificar_avisos(avisar)
                except Exception as erro:  # noqa: BLE001
                    log.warning("Falha nos avisos: %s", erro)
                time.sleep(15)

        self._lembretes = threading.Thread(target=ciclo, daemon=True, name="lembretes")
        self._lembretes.start()

    def iniciar_copiados(self) -> None:
        """Guarda no histórico o que for copiado (Ctrl+C). Opt-in: só roda se
        [copiados] ativo = true, porque ler a área de transferência é sensível."""
        if not self.config.get("copiados", "ativo", False):
            return
        if self._copiados and self._copiados.is_alive():
            return
        try:
            import pyperclip
        except ImportError:
            log.info("Histórico de copiados pedido, mas pyperclip não está instalado.")
            return
        limite = int(self.config.get("copiados", "limite", 100) or 100)
        intervalo = float(self.config.get("copiados", "intervalo_seg", 2) or 2)

        def ciclo():
            ultimo = None
            while True:
                try:
                    atual = pyperclip.paste()
                    if atual and atual != ultimo:
                        ultimo = atual
                        self.banco.guardar_copiado(atual, limite)
                except Exception as erro:  # noqa: BLE001
                    log.debug("Falha ao ler a área de transferência: %s", erro)
                time.sleep(intervalo)

        self._copiados = threading.Thread(target=ciclo, daemon=True, name="copiados")
        self._copiados.start()


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
