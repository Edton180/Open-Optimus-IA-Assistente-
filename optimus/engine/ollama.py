"""Motor Ollama (http://127.0.0.1:11434). Roda modelos locais no Windows, Linux e macOS."""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

from optimus.engine.base import ChamadaFerramenta, ErroMotor, Motor, Resposta, limpar_pensamento


class MotorOllama(Motor):
    nome = "ollama"

    def __init__(self, url: str = "http://127.0.0.1:11434", tempo_limite: float = 600.0):
        self.url = url.rstrip("/")
        self.tempo_limite = tempo_limite

    def _opcoes(self, opcoes: dict[str, Any] | None) -> tuple[dict[str, Any], Any]:
        opcoes = dict(opcoes or {})
        opcoes.pop("pensar", None)
        manter = opcoes.pop("manter_carregado", None)
        traduzir = {"contexto": "num_ctx", "threads": "num_thread", "temperatura": "temperature"}
        saida = {}
        for chave, valor in opcoes.items():
            if valor in (None, 0, ""):
                continue
            saida[traduzir.get(chave, chave)] = valor
        return saida, manter

    def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None,
                  ao_pedaco=None, cancelado=None) -> Resposta:
        """Conversa em modo streaming: o texto chega aos pedaços (ao_pedaco) enquanto o
        modelo escreve, então a interface mostra e fala a resposta sem esperar o fim.

        `pensar` (nas opções) liga o raciocínio interno de modelos como qwen3/deepseek-r1.
        Desligado por padrão: em CPU ele multiplica o tempo de resposta.
        """
        opcoes = dict(opcoes or {})
        pensar = bool(opcoes.pop("pensar", False))
        options, manter = self._opcoes(opcoes)
        corpo: dict[str, Any] = {
            "model": modelo,
            "messages": _para_ollama(mensagens),
            "stream": True,
            "options": options,
            "think": pensar,
        }
        if manter:
            corpo["keep_alive"] = manter
        if ferramentas:
            corpo["tools"] = ferramentas
        texto: list[str] = []
        chamadas: list[ChamadaFerramenta] = []
        final: dict[str, Any] = {}
        for tentativa in range(3):
            try:
                with httpx.stream("POST", f"{self.url}/api/chat", json=corpo,
                                  timeout=httpx.Timeout(self.tempo_limite, connect=5)) as r:
                    if r.status_code == 400:
                        erro = r.read().decode(errors="replace")
                        # Modelo sem suporte a "think" ou a ferramentas: tenta sem.
                        if "think" in erro.lower() and "think" in corpo:
                            corpo.pop("think")
                            continue
                        if ferramentas and "tools" in corpo:
                            corpo.pop("tools")
                            continue
                        raise ErroMotor(f"Ollama respondeu 400: {erro[:300]}")
                    if r.status_code == 404:
                        raise ErroMotor(f"O modelo '{modelo}' não está instalado no Ollama. "
                                        f"Baixe com: ollama pull {modelo}")
                    if r.status_code >= 400:
                        raise ErroMotor(f"Ollama respondeu {r.status_code}: "
                                        f"{r.read().decode(errors='replace')[:300]}")
                    for linha in r.iter_lines():
                        if cancelado is not None and cancelado():
                            break
                        if not linha:
                            continue
                        dados = json.loads(linha)
                        if dados.get("error"):
                            raise ErroMotor(f"Ollama: {dados['error']}")
                        mensagem = dados.get("message") or {}
                        pedaco = mensagem.get("content") or ""
                        if pedaco:
                            texto.append(pedaco)
                            if ao_pedaco is not None:
                                ao_pedaco(pedaco)
                        for chamada in mensagem.get("tool_calls") or []:
                            funcao = chamada.get("function", {})
                            argumentos = funcao.get("arguments") or {}
                            if isinstance(argumentos, str):
                                try:
                                    argumentos = json.loads(argumentos)
                                except json.JSONDecodeError:
                                    argumentos = {}
                            if funcao.get("name"):
                                chamadas.append(ChamadaFerramenta(nome=funcao["name"],
                                                                  argumentos=argumentos))
                        if dados.get("done"):
                            final = dados
                break
            except httpx.HTTPError as erro:
                raise ErroMotor(f"Não consegui falar com o Ollama em {self.url}. Ele está "
                                f"aberto? ({erro})") from erro
        velocidade = 0.0
        if final.get("eval_count") and final.get("eval_duration"):
            velocidade = final["eval_count"] / (final["eval_duration"] / 1e9)
        return Resposta(
            texto=limpar_pensamento("".join(texto)),
            chamadas=chamadas,
            modelo=modelo,
            tokens_por_segundo=round(velocidade, 1),
        )

    def transmitir(self, mensagens, modelo, opcoes=None) -> Iterator[str]:
        options, manter = self._opcoes(opcoes)
        corpo = {"model": modelo, "messages": _para_ollama(mensagens), "stream": True,
                 "options": options, "think": False}
        if manter:
            corpo["keep_alive"] = manter
        dentro_pensamento = False
        try:
            with httpx.stream("POST", f"{self.url}/api/chat", json=corpo,
                              timeout=self.tempo_limite) as resposta:
                resposta.raise_for_status()
                for linha in resposta.iter_lines():
                    if not linha:
                        continue
                    pedaco = json.loads(linha).get("message", {}).get("content", "")
                    if "<think>" in pedaco:
                        dentro_pensamento = True
                    if dentro_pensamento:
                        if "</think>" in pedaco:
                            dentro_pensamento = False
                            pedaco = pedaco.split("</think>", 1)[1]
                        else:
                            continue
                    if pedaco:
                        yield pedaco
        except httpx.HTTPError as erro:
            raise ErroMotor(f"Falha no Ollama: {erro}") from erro

    def disponivel(self) -> bool:
        try:
            return httpx.get(f"{self.url}/api/version", timeout=1.5).status_code == 200
        except httpx.HTTPError:
            return False

    def modelos(self) -> list[str]:
        try:
            dados = httpx.get(f"{self.url}/api/tags", timeout=5).json()
        except (httpx.HTTPError, ValueError):
            return []
        return sorted(m.get("name", "") for m in dados.get("models", []))

    def baixar(self, modelo: str, progresso=None) -> bool:
        try:
            with httpx.stream("POST", f"{self.url}/api/pull", json={"model": modelo},
                              timeout=None) as resposta:
                if resposta.status_code != 200:
                    return False
                for linha in resposta.iter_lines():
                    if not linha:
                        continue
                    dados = json.loads(linha)
                    if dados.get("error"):
                        return False
                    if progresso:
                        progresso(dados)
                    if dados.get("status") == "success":
                        return True
        except httpx.HTTPError:
            return False
        return True


def _para_ollama(mensagens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saida = []
    for m in mensagens:
        item = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("tool_calls"):
            item["tool_calls"] = [
                {"function": {"name": c["function"]["name"],
                              "arguments": c["function"]["arguments"]}}
                for c in m["tool_calls"]
            ]
        if m.get("images"):
            item["images"] = m["images"]
        saida.append(item)
    return saida
