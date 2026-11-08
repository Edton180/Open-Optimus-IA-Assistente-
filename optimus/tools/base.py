"""Base das ferramentas: cada ferramenta tem nome, descrição, parâmetros e nível de risco."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from optimus.safety import LIVRE, Avaliacao


def no_android() -> bool:
    return "ANDROID_ROOT" in os.environ or "com.termux" in os.environ.get("PREFIX", "")


def sistema() -> str:
    if no_android():
        return "android"
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


@dataclass
class Contexto:
    config: Any
    banco: Any = None
    pasta_trabalho: Path = field(default_factory=Path.home)
    perfil: Any = None
    agente: Any = None  # o agente que está usando a ferramenta (para sub-agentes)


Risco = int | Callable[[dict[str, Any], Contexto], Avaliacao]


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict[str, Any]
    funcao: Callable[..., Any]
    grupo: str = "geral"
    risco: Risco = LIVRE
    obrigatorios: list[str] = field(default_factory=list)

    def esquema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.nome,
                "description": self.descricao,
                "parameters": {
                    "type": "object",
                    "properties": self.parametros,
                    "required": self.obrigatorios,
                },
            },
        }

    def avaliar(self, argumentos: dict[str, Any], contexto: Contexto) -> Avaliacao:
        if callable(self.risco):
            return self.risco(argumentos, contexto)
        return Avaliacao(self.risco, self.descricao)

    def executar(self, argumentos: dict[str, Any], contexto: Contexto) -> str:
        try:
            resultado = self.funcao(contexto, **argumentos)
        except TypeError as erro:
            resultado = {"erro": f"Parâmetros inválidos para {self.nome}: {erro}"}
        except Exception as erro:  # noqa: BLE001 - a ferramenta nunca derruba o agente
            resultado = {"erro": f"{type(erro).__name__}: {erro}"}
        if isinstance(resultado, str):
            return resultado
        return json.dumps(resultado, ensure_ascii=False, default=str)


_REGISTRO: dict[str, Ferramenta] = {}


def ferramenta(nome: str, descricao: str, parametros: dict[str, Any] | None = None,
               grupo: str = "geral", risco: Risco = LIVRE,
               obrigatorios: list[str] | None = None):
    """Decorador para registrar uma ferramenta (também usado pelos plugins)."""

    def registrar(funcao):
        _REGISTRO[nome] = Ferramenta(
            nome=nome, descricao=descricao, parametros=parametros or {}, funcao=funcao,
            grupo=grupo, risco=risco,
            obrigatorios=obrigatorios if obrigatorios is not None else list(parametros or {}),
        )
        return funcao

    return registrar


def registradas() -> dict[str, Ferramenta]:
    return dict(_REGISTRO)


def texto(descricao: str) -> dict[str, str]:
    return {"type": "string", "description": descricao}


def numero(descricao: str) -> dict[str, str]:
    return {"type": "integer", "description": descricao}


def resolver(contexto: Contexto, caminho: str) -> Path:
    alvo = Path(os.path.expandvars(str(caminho))).expanduser()
    if not alvo.is_absolute():
        alvo = contexto.pasta_trabalho / alvo
    return alvo.resolve()
