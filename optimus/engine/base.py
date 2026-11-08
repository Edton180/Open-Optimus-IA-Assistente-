"""Tipos comuns dos motores e leitura de chamadas de ferramenta em texto.

Modelos pequenos às vezes não usam a API de ferramentas e escrevem a chamada no texto,
por exemplo dentro de <tool_call>...</tool_call> ou num bloco ```json. O Optimus
entende os dois jeitos, o que deixa modelos de 1 a 4 bilhões de parâmetros úteis.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class ChamadaFerramenta:
    nome: str
    argumentos: dict[str, Any]
    id: str = field(default_factory=lambda: "chamada_" + uuid.uuid4().hex[:8])


@dataclass
class Resposta:
    texto: str = ""
    chamadas: list[ChamadaFerramenta] = field(default_factory=list)
    modelo: str = ""
    tokens_por_segundo: float = 0.0


class ErroMotor(RuntimeError):
    pass


class Motor:
    nome = "base"

    def conversar(
        self,
        mensagens: list[dict[str, Any]],
        modelo: str,
        ferramentas: list[dict[str, Any]] | None = None,
        opcoes: dict[str, Any] | None = None,
        ao_pedaco=None,
        cancelado=None,
    ) -> Resposta:
        """ao_pedaco(texto): recebe a resposta aos pedaços (streaming), se o motor suportar.
        cancelado(): devolve True quando o usuário cancelou o pedido."""
        raise NotImplementedError

    def transmitir(
        self, mensagens: list[dict[str, Any]], modelo: str, opcoes: dict[str, Any] | None = None
    ) -> Iterator[str]:
        """Resposta em pedaços (para falar frase por frase). Padrão: tudo de uma vez."""
        yield self.conversar(mensagens, modelo, None, opcoes).texto

    def disponivel(self) -> bool:
        return False

    def modelos(self) -> list[str]:
        return []

    def baixar(self, modelo: str, progresso=None) -> bool:
        return False


_TAG = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_BLOCO = re.compile(r"```(?:json|tool)?\s*(\{.*?\})\s*```", re.DOTALL)
_PENSAMENTO = re.compile(r"<think>.*?</think>", re.DOTALL)


def limpar_pensamento(texto: str) -> str:
    """Remove o raciocínio interno (<think>) que alguns modelos escrevem."""
    texto = _PENSAMENTO.sub("", texto)
    if "</think>" in texto:
        texto = texto.split("</think>", 1)[1]
    return texto.strip()


def _converter(obj: Any, nomes: set[str]) -> ChamadaFerramenta | None:
    if not isinstance(obj, dict):
        return None
    nome = obj.get("name") or obj.get("nome") or obj.get("tool") or obj.get("ferramenta")
    args = obj.get("arguments", obj.get("argumentos", obj.get("parameters", obj.get("args", {}))))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"texto": args}
    if isinstance(nome, str) and nome in nomes and isinstance(args, dict):
        return ChamadaFerramenta(nome=nome, argumentos=args)
    return None


def extrair_chamadas_do_texto(texto: str, nomes: set[str]) -> tuple[str, list[ChamadaFerramenta]]:
    """Procura chamadas de ferramenta escritas no texto. Devolve (texto restante, chamadas)."""
    chamadas: list[ChamadaFerramenta] = []
    restante = texto
    for padrao in (_TAG, _BLOCO):
        for achado in padrao.finditer(texto):
            try:
                chamada = _converter(json.loads(achado.group(1)), nomes)
            except json.JSONDecodeError:
                chamada = None
            if chamada:
                chamadas.append(chamada)
                restante = restante.replace(achado.group(0), "")
        if chamadas:
            return restante.strip(), chamadas
    bruto = texto.strip()
    if bruto.startswith("{") and bruto.endswith("}"):
        try:
            chamada = _converter(json.loads(bruto), nomes)
        except json.JSONDecodeError:
            chamada = None
        if chamada:
            return "", [chamada]
    return texto, []
