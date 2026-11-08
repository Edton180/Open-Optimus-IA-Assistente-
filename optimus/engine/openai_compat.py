"""Motor para qualquer servidor compatível com a API da OpenAI.

Serve para llama.cpp (llama-server), LM Studio, vLLM, LocalAI, Jan e também para
serviços na nuvem, se o usuário quiser (basta trocar a URL e a chave).
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

from optimus.engine.base import ChamadaFerramenta, ErroMotor, Motor, Resposta, limpar_pensamento


class MotorOpenAI(Motor):
    nome = "openai"

    def __init__(self, url: str = "http://127.0.0.1:8080/v1", chave_api: str = "",
                 tempo_limite: float = 600.0):
        url = url.rstrip("/")
        self.url = url if url.endswith("/v1") else url + "/v1"
        self.chave_api = chave_api
        self.tempo_limite = tempo_limite

    def _cabecalhos(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.chave_api}"} if self.chave_api else {}

    def _corpo(self, mensagens, modelo, opcoes) -> dict[str, Any]:
        opcoes = opcoes or {}
        corpo: dict[str, Any] = {"model": modelo, "messages": _para_openai(mensagens)}
        if opcoes.get("temperatura") is not None:
            corpo["temperature"] = opcoes["temperatura"]
        return corpo

    def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None,
                  ao_pedaco=None, cancelado=None) -> Resposta:
        """Streaming (SSE) com ferramentas: junta os pedaços de texto e de tool_calls."""
        corpo = self._corpo(mensagens, modelo, opcoes)
        corpo["stream"] = True
        if ferramentas:
            corpo["tools"] = ferramentas
        texto: list[str] = []
        parciais: dict[int, dict[str, str]] = {}
        for _ in range(2):
            try:
                with httpx.stream("POST", f"{self.url}/chat/completions", json=corpo,
                                  headers=self._cabecalhos(),
                                  timeout=httpx.Timeout(self.tempo_limite, connect=8)) as r:
                    if r.status_code in (400, 422) and "tools" in corpo:
                        r.read()
                        corpo.pop("tools")  # servidor sem ferramentas: o agente lê do texto
                        continue
                    if r.status_code >= 400:
                        raise ErroMotor(f"Servidor respondeu {r.status_code}: "
                                        f"{r.read().decode(errors='replace')[:300]}")
                    for linha in r.iter_lines():
                        if cancelado is not None and cancelado():
                            break
                        if not linha.startswith("data:"):
                            continue
                        dado = linha[5:].strip()
                        if dado == "[DONE]":
                            break
                        try:
                            pacote = json.loads(dado)
                        except json.JSONDecodeError:
                            continue
                        if not pacote.get("choices"):
                            continue
                        delta = pacote["choices"][0].get("delta") or {}
                        if delta.get("content"):
                            texto.append(delta["content"])
                            if ao_pedaco is not None:
                                ao_pedaco(delta["content"])
                        for parte in delta.get("tool_calls") or []:
                            atual = parciais.setdefault(int(parte.get("index", 0)),
                                                        {"id": "", "nome": "", "args": ""})
                            atual["id"] = parte.get("id") or atual["id"]
                            funcao = parte.get("function") or {}
                            atual["nome"] += funcao.get("name") or ""
                            atual["args"] += funcao.get("arguments") or ""
                break
            except httpx.HTTPError as erro:
                raise ErroMotor(f"Não consegui falar com {self.url}: {erro}") from erro
        chamadas = []
        for _, parte in sorted(parciais.items()):
            try:
                argumentos = json.loads(parte["args"] or "{}")
            except json.JSONDecodeError:
                argumentos = {}
            if parte["nome"]:
                chamadas.append(ChamadaFerramenta(nome=parte["nome"], argumentos=argumentos,
                                                  id=parte["id"] or "chamada"))
        return Resposta(texto=limpar_pensamento("".join(texto)), chamadas=chamadas,
                        modelo=modelo)

    def transmitir(self, mensagens, modelo, opcoes=None) -> Iterator[str]:
        corpo = self._corpo(mensagens, modelo, opcoes)
        corpo["stream"] = True
        try:
            with httpx.stream("POST", f"{self.url}/chat/completions", json=corpo,
                              headers=self._cabecalhos(), timeout=self.tempo_limite) as resposta:
                resposta.raise_for_status()
                for linha in resposta.iter_lines():
                    if not linha.startswith("data:"):
                        continue
                    dado = linha[5:].strip()
                    if dado == "[DONE]":
                        break
                    delta = json.loads(dado)["choices"][0].get("delta", {})
                    if delta.get("content"):
                        yield delta["content"]
        except httpx.HTTPError as erro:
            raise ErroMotor(f"Falha no servidor: {erro}") from erro

    def disponivel(self) -> bool:
        try:
            return httpx.get(f"{self.url}/models", headers=self._cabecalhos(),
                             timeout=2).status_code == 200
        except httpx.HTTPError:
            return False

    def modelos(self) -> list[str]:
        try:
            dados = httpx.get(f"{self.url}/models", headers=self._cabecalhos(), timeout=5).json()
        except (httpx.HTTPError, ValueError):
            return []
        return sorted(m.get("id", "") for m in dados.get("data", []))


def _para_openai(mensagens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saida = []
    for m in mensagens:
        item = {k: v for k, v in m.items() if k in ("role", "content", "tool_call_id", "name")}
        if m["role"] != "tool":
            item.pop("name", None)
        if m.get("tool_calls"):
            item["tool_calls"] = [
                {"id": c.get("id", "chamada"), "type": "function",
                 "function": {"name": c["function"]["name"],
                              "arguments": c["function"]["arguments"]
                              if isinstance(c["function"]["arguments"], str)
                              else json.dumps(c["function"]["arguments"], ensure_ascii=False)}}
                for c in m["tool_calls"]
            ]
        saida.append(item)
    return saida
