"""Motores de IA: Ollama, servidores compatíveis com OpenAI e modo demonstração."""

from __future__ import annotations

from optimus.engine.base import ChamadaFerramenta, Motor, Resposta
from optimus.engine.demo import MotorDemo
from optimus.engine.ollama import MotorOllama
from optimus.engine.openai_compat import MotorOpenAI
from optimus.engine.rede import PROVEDORES, Destino, MotorRede, criar_destino


def criar_motor_principal(config) -> Motor:
    backend = (config.get("motor", "backend") or "ollama").lower()
    url = config.get("motor", "url")
    if backend == "demo":
        return MotorDemo()
    if backend in PROVEDORES and backend != "ollama":
        if not url or "11434" in url:
            url = PROVEDORES[backend]["url"]
        return MotorOpenAI(url=url, chave_api=config.get("motor", "chave_api") or "")
    if backend in ("openai", "vllm", "nuvem"):
        return MotorOpenAI(url=url, chave_api=config.get("motor", "chave_api") or "")
    return MotorOllama(url=url)


def criar_motor(config) -> Motor:
    """Motor do PC e, se houver, os outros computadores e IAs cadastrados em [[destinos]]."""
    principal = criar_motor_principal(config)
    extras = config.dados.get("destinos") or []
    if not extras or isinstance(principal, MotorDemo):
        return principal
    destinos = [Destino(nome="Este PC", motor=principal, prioridade=5)]
    destinos += [criar_destino(d) for d in extras if d.get("ativo", True)]
    return MotorRede(destinos)


__all__ = ["ChamadaFerramenta", "Motor", "Resposta", "criar_motor", "MotorOllama",
           "MotorOpenAI", "MotorDemo"]
