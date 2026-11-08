"""Rede de motores: outros computadores e outras IAs.

O usuário pode cadastrar vários destinos (o próprio PC, outro PC da casa com placa de
vídeo melhor, ou um provedor na nuvem). O Optimus testa quem está ligado e manda o pedido
para o melhor destino disponível, na ordem de prioridade. Se um cair no meio, tenta o
próximo. Assim um notebook fraco pode usar a placa de vídeo do PC da sala.

Exemplo no config.toml:

    [[destinos]]
    nome = "PC da sala"
    backend = "ollama"
    url = "http://192.168.0.20:11434"
    modelo = "qwen3.5:27b"
    prioridade = 1

    [[destinos]]
    nome = "OpenRouter"
    backend = "openai"
    url = "https://openrouter.ai/api/v1"
    chave_api = "sk-..."
    modelo = "qualquer-modelo"
    prioridade = 9
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from optimus.engine.base import ErroMotor, Motor, Resposta
from optimus.engine.ollama import MotorOllama
from optimus.engine.openai_compat import MotorOpenAI

# Provedores conhecidos com API compatível com a da OpenAI. O usuário só põe a chave.
PROVEDORES: dict[str, dict[str, str]] = {
    "openai": {"url": "https://api.openai.com/v1", "modelo": "gpt-5-mini"},
    "anthropic": {"url": "https://api.anthropic.com/v1", "modelo": "claude-sonnet-5-5"},
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "modelo": "gemini-2.5-flash"},
    "groq": {"url": "https://api.groq.com/openai/v1", "modelo": "llama-3.3-70b-versatile"},
    "openrouter": {"url": "https://openrouter.ai/api/v1", "modelo": "openrouter/auto"},
    "deepseek": {"url": "https://api.deepseek.com/v1", "modelo": "deepseek-chat"},
    "mistral": {"url": "https://api.mistral.ai/v1", "modelo": "mistral-large-latest"},
    "lmstudio": {"url": "http://127.0.0.1:1234/v1", "modelo": ""},
    "llamacpp": {"url": "http://127.0.0.1:8080/v1", "modelo": ""},
}


@dataclass
class Destino:
    nome: str
    motor: Motor
    modelo: str = ""
    prioridade: int = 5
    local: bool = True
    _ultimo_teste: float = field(default=float("-inf"), repr=False)  # nunca testado
    _ligado: bool = field(default=False, repr=False)

    def ligado(self, cache_segundos: float = 30.0) -> bool:
        agora = time.monotonic()
        # Destino desligado só é testado de novo depois de 2 minutos, para não atrasar pedidos.
        espera = cache_segundos if self._ligado else 120.0
        if agora - self._ultimo_teste > espera:
            self._ligado = self.motor.disponivel()
            self._ultimo_teste = agora
        return self._ligado

    def descartar(self) -> None:
        self._ligado = False
        self._ultimo_teste = time.monotonic()


def criar_destino(dados: dict[str, Any]) -> Destino:
    backend = (dados.get("backend") or "ollama").lower()
    url = dados.get("url", "")
    modelo = dados.get("modelo", "")
    if backend in PROVEDORES and not url:
        url = PROVEDORES[backend]["url"]
        modelo = modelo or PROVEDORES[backend]["modelo"]
    if backend == "ollama":
        motor: Motor = MotorOllama(url or "http://127.0.0.1:11434")
    else:
        motor = MotorOpenAI(url, chave_api=dados.get("chave_api", ""))
    local = any(p in url for p in ("127.0.0.1", "localhost", "192.168.", "10.", "172.16."))
    return Destino(nome=dados.get("nome") or backend, motor=motor, modelo=modelo,
                   prioridade=int(dados.get("prioridade", 5)), local=local)


class MotorRede(Motor):
    """Encaminha para o primeiro destino ligado; o modelo de cada destino vale sobre o geral."""

    nome = "rede"

    def __init__(self, destinos: list[Destino]):
        self.destinos = sorted(destinos, key=lambda d: d.prioridade)
        self.ultimo_destino: Destino | None = None

    def _candidatos(self) -> list[Destino]:
        return [d for d in self.destinos if d.ligado()]

    def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None,
                  ao_pedaco=None, cancelado=None) -> Resposta:
        erros = []
        for destino in self._candidatos():
            enviados: list[str] = []

            def repassar(pedaco, enviados=enviados):
                enviados.append(pedaco)
                if ao_pedaco is not None:
                    ao_pedaco(pedaco)

            try:
                resposta = destino.motor.conversar(mensagens, destino.modelo or modelo,
                                                   ferramentas, opcoes, ao_pedaco=repassar,
                                                   cancelado=cancelado)
                self.ultimo_destino = destino
                resposta.modelo = f"{resposta.modelo} @ {destino.nome}"
                return resposta
            except ErroMotor as erro:
                destino.descartar()
                erros.append(f"{destino.nome}: {erro}")
                if enviados:  # já mostrou parte da resposta: não repete em outro destino
                    break
        raise ErroMotor("Nenhum destino respondeu. " + " | ".join(erros or ["todos desligados"]))

    def transmitir(self, mensagens, modelo, opcoes=None):
        for destino in self._candidatos():
            try:
                yield from destino.motor.transmitir(mensagens, destino.modelo or modelo, opcoes)
                self.ultimo_destino = destino
                return
            except ErroMotor:
                destino.descartar()
        raise ErroMotor("Nenhum destino respondeu.")

    def disponivel(self) -> bool:
        return bool(self._candidatos())

    def modelos(self) -> list[str]:
        nomes: list[str] = []
        for destino in self._candidatos():
            nomes.extend(f"{m}" for m in destino.motor.modelos())
        return sorted(set(nomes))

    def baixar(self, modelo, progresso=None) -> bool:
        for destino in self._candidatos():
            if destino.local and destino.motor.baixar(modelo, progresso):
                return True
        return False

    def estado(self) -> list[dict[str, Any]]:
        return [{"nome": d.nome, "modelo": d.modelo, "prioridade": d.prioridade,
                 "ligado": d.ligado(), "local": d.local} for d in self.destinos]
