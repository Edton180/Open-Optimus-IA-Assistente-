"""Servidor MCP do Optimus: outros programas de IA (Claude Desktop, Cursor, VS Code, LM Studio…)
usam as ferramentas do Optimus como se fossem deles.

    optimus mcp-servidor                       # ferramentas do estúdio de voz
    optimus mcp-servidor --grupos estudio,produtividade

Fala MCP por stdio (JSON-RPC 2.0, uma mensagem por linha). No programa de IA, adicione:

    {"mcpServers": {"optimus": {"command": "optimus", "args": ["mcp-servidor"]}}}

Ferramentas de risco crítico (apagar arquivos, comandos do sistema…) nunca são expostas, e
as de risco moderado (dublar, legendar no vídeo…) podem ser desligadas com `--so-livres`, já
que o programa que chama não passa pela confirmação do Optimus.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from optimus import __version__
from optimus.mcp_cliente import VERSAO_PROTOCOLO
from optimus.safety import CRITICO, MODERADO

VERSOES = ("2025-06-18", "2025-03-26", "2024-11-05")


class Servidor:
    def __init__(self, config=None, grupos: list[str] | None = None, moderadas: bool = True,
                 pasta: str | Path | None = None):
        import optimus.tools  # noqa: F401 - registra as ferramentas
        from optimus.tools.base import Contexto, registradas

        self.grupos = [g.strip() for g in (grupos or ["estudio"]) if g.strip()]
        self.limite = CRITICO if moderadas else MODERADO
        pasta_trabalho = Path(pasta).expanduser() if pasta else Path.home()
        self.ctx = Contexto(config=config, pasta_trabalho=pasta_trabalho)
        self.ferramentas = {}
        for nome, f in sorted(registradas().items()):
            if "*" not in self.grupos and f.grupo not in self.grupos:
                continue
            nivel = f.avaliar({}, self.ctx).nivel if callable(f.risco) else f.risco
            if nivel >= self.limite:  # ex.: clonar voz pede confirmação no próprio Optimus
                continue
            self.ferramentas[nome] = f

    # ------------------------------------------------------------------ protocolo
    def _lista(self) -> list[dict]:
        saida = []
        for f in self.ferramentas.values():
            esquema = f.esquema()["function"]
            saida.append({"name": f.nome, "description": f.descricao,
                          "inputSchema": esquema["parameters"]})
        return saida

    def _chamar(self, nome: str, argumentos: dict) -> dict:
        f = self.ferramentas.get(nome)
        if f is None:
            return {"content": [{"type": "text", "text": f"Ferramenta desconhecida: {nome}"}],
                    "isError": True}
        avaliacao = f.avaliar(argumentos, self.ctx)
        if avaliacao.nivel >= self.limite:
            return {"content": [{"type": "text", "text": "Ação de risco alto: faça pelo "
                                 f"próprio Optimus. ({avaliacao.motivo})"}], "isError": True}
        texto = f.executar(argumentos, self.ctx)
        erro = False
        try:
            dados = json.loads(texto)
            erro = isinstance(dados, dict) and bool(dados.get("erro"))
        except ValueError:
            dados = None
        resposta: dict[str, Any] = {"content": [{"type": "text", "text": texto}],
                                    "isError": erro}
        if isinstance(dados, dict):
            resposta["structuredContent"] = dados
        return resposta

    def tratar(self, mensagem: dict) -> dict | None:
        """Uma mensagem JSON-RPC → a resposta (ou None para notificações)."""
        metodo = mensagem.get("method")
        ident = mensagem.get("id")
        params = mensagem.get("params") or {}
        if ident is None:  # notificação (initialized, cancelled…): sem resposta
            return None
        try:
            if metodo == "initialize":
                pedida = str(params.get("protocolVersion") or VERSAO_PROTOCOLO)
                resultado: Any = {
                    "protocolVersion": pedida if pedida in VERSOES else VERSAO_PROTOCOLO,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "open-optimus", "version": __version__},
                    "instructions": "Ferramentas do Open Optimus: estúdio de voz (narração, "
                                    "clonagem com consentimento, legendas, tradução, dublagem) "
                                    "e outras, conforme os grupos ligados.",
                }
            elif metodo == "ping":
                resultado = {}
            elif metodo == "tools/list":
                resultado = {"tools": self._lista()}
            elif metodo == "tools/call":
                resultado = self._chamar(str(params.get("name", "")),
                                         params.get("arguments") or {})
            elif metodo in ("resources/list", "prompts/list"):
                resultado = {metodo.split("/")[0]: []}
            else:
                return {"jsonrpc": "2.0", "id": ident,
                        "error": {"code": -32601, "message": f"Método desconhecido: {metodo}"}}
        except Exception as erro:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": ident,
                    "error": {"code": -32603, "message": f"{type(erro).__name__}: {erro}"}}
        return {"jsonrpc": "2.0", "id": ident, "result": resultado}

    def rodar(self, entrada: TextIO | None = None, saida: TextIO | None = None) -> None:
        entrada = entrada or sys.stdin
        saida = saida or sys.stdout
        for linha in entrada:
            linha = linha.strip()
            if not linha:
                continue
            try:
                mensagem = json.loads(linha)
            except ValueError:
                resposta: Any = {"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32700, "message": "JSON inválido"}}
            else:
                if isinstance(mensagem, list):
                    resposta = [r for r in (self.tratar(m) for m in mensagem
                                            if isinstance(m, dict)) if r] or None
                else:
                    resposta = self.tratar(mensagem) if isinstance(mensagem, dict) else None
            if resposta:
                saida.write(json.dumps(resposta, ensure_ascii=False, default=str) + "\n")
                saida.flush()


def principal(config=None, grupos: list[str] | None = None, moderadas: bool = True,
              pasta: str | None = None) -> int:
    # Tudo que não for protocolo vai para o stderr, para não estragar a conversa por stdio
    real = sys.stdout
    sys.stdout = sys.stderr
    try:
        Servidor(config, grupos, moderadas, pasta).rodar(sys.stdin, real)
    finally:
        sys.stdout = real
    return 0
