"""Motores de IA: Ollama, servidores compatíveis com OpenAI e modo demonstração."""

from __future__ import annotations

from optimus.engine.base import ChamadaFerramenta, Motor, Resposta
from optimus.engine.demo import MotorDemo
from optimus.engine.ollama import MotorOllama
from optimus.engine.openai_compat import MotorOpenAI
from optimus.engine.rede import PROVEDORES, Destino, MotorRede, criar_destino, destinos_gratis


def criar_motor_principal(config) -> Motor:
    backend = (config.get("motor", "backend") or "ollama").lower()
    url = config.get("motor", "url")
    espera = float(config.get("motor", "tempo_sem_resposta", 120) or 120)
    if backend == "demo":
        return MotorDemo()
    if backend == "gratis":
        return MotorRede(destinos_gratis(config))
    if backend in PROVEDORES and backend != "ollama":
        if not url or "11434" in url:
            url = PROVEDORES[backend]["url"]
        motor = MotorOpenAI(url=url, chave_api=config.get("motor", "chave_api") or "",
                            tempo_sem_resposta=espera)
        local = any(p in url for p in ("127.0.0.1", "localhost"))
        if local:
            return motor
        # Na nuvem, o modelo do perfil de hardware (nome do Ollama) não serve: usa o padrão
        # do provedor ou escolhe um na lista dele, a menos que motor.modelo esteja definido.
        return MotorRede([Destino(nome=backend, motor=motor, local=False, testar=False,
                                  modelo=config.get("motor", "modelo", "")
                                  or PROVEDORES[backend]["modelo"])])
    if backend in ("openai", "vllm", "nuvem"):
        return MotorOpenAI(url=url, chave_api=config.get("motor", "chave_api") or "",
                           tempo_sem_resposta=espera)
    return MotorOllama(url=url, tempo_sem_resposta=espera)


def criar_motor(config) -> Motor:
    """Motor do PC e, se houver, os outros computadores e IAs cadastrados em [[destinos]]."""
    principal = criar_motor_principal(config)
    extras = config.dados.get("destinos") or []
    if not extras or isinstance(principal, MotorDemo):
        return principal
    if isinstance(principal, MotorRede):
        principal.destinos = sorted(principal.destinos + [criar_destino(d) for d in extras
                                                          if d.get("ativo", True)],
                                    key=lambda d: d.prioridade)
        return principal
    destinos = [Destino(nome="Este PC", motor=principal, prioridade=5)]
    destinos += [criar_destino(d) for d in extras if d.get("ativo", True)]
    return MotorRede(destinos)


__all__ = [
    "ChamadaFerramenta",
    "Motor",
    "MotorDemo",
    "MotorOllama",
    "MotorOpenAI",
    "Resposta",
    "criar_motor",
]
