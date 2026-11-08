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

    def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None) -> Resposta:
        corpo = self._corpo(mensagens, modelo, opcoes)
        if ferramentas:
            corpo["tools"] = ferramentas
        try:
            resposta = httpx.post(f"{self.url}/chat/completions", json=corpo,
                                  headers=self._cabecalhos(), timeout=self.tempo_limite)
            if resposta.status_code in (400, 422) and ferramentas:
                corpo.pop("tools", None)
                resposta = httpx.post(f"{self.url}/chat/completions", json=corpo,
                                      headers=self._cabecalhos(), timeout=self.tempo_limite)
            resposta.raise_for_status()
        except httpx.HTTPStatusError as erro:
            raise ErroMotor(f"Servidor respondeu {erro.response.status_code}: "
                            f"{erro.response.text[:300]}") from erro
        except httpx.HTTPError as erro:
            raise ErroMotor(f"Não consegui falar com {self.url}: {erro}") from erro
        escolha = resposta.json()["choices"][0]["message"]
        chamadas = []
        for chamada in escolha.get("tool_calls") or []:
            funcao = chamada.get("function", {})
            try:
                argumentos = json.loads(funcao.get("arguments") or "{}")
            except json.JSONDecodeError:
                argumentos = {}
            chamadas.append(ChamadaFerramenta(nome=funcao.get("name", ""), argumentos=argumentos,
                                              id=chamada.get("id") or "chamada"))
        return Resposta(texto=limpar_pensamento(escolha.get("content") or ""), chamadas=chamadas,
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
                             timeout=3).status_code == 200
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
