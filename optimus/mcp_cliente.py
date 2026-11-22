"""Cliente MCP (Model Context Protocol): liga o Optimus a outros serviços e apps.

Com MCP, qualquer serviço que tenha um servidor MCP (GitHub, Notion, Zapier, Google Drive,
bancos de dados, o sistema de arquivos...) vira ferramenta do Optimus, sem código novo. Cada
ferramenta do servidor aparece para a IA como `mcp_<servidor>_<ferramenta>`.

Dois jeitos de conectar, no `config.toml`:

    [[mcp]]
    nome = "arquivos"
    comando = ["npx", "-y", "@modelcontextprotocol/server-filesystem", "C:/Users/eu/Documentos"]

    [[mcp]]
    nome = "notion"
    url = "https://exemplo.com/mcp"
    token = "cofre:mcp.notion.token"   # chave no cofre do sistema (optimus chaves)
    risco = "critico"                  # livre | moderado (padrão) | critico

`comando` roda um servidor local (stdio). `url` fala com um servidor remoto (HTTP). Por
segurança, toda ferramenta MCP é tratada como **moderada** por padrão; use `risco = "critico"`
para o Optimus pedir confirmação antes de cada uso.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import shlex
import subprocess
import threading
from typing import Any

from optimus.safety import CRITICO, LIVRE, MODERADO

log = logging.getLogger(__name__)

VERSAO_PROTOCOLO = "2025-06-18"
CLIENTE = {"name": "open-optimus", "version": "1"}
_RISCOS = {"livre": LIVRE, "moderado": MODERADO, "critico": CRITICO, "crítico": CRITICO}


class ErroMCP(RuntimeError):
    pass


# ---------------------------------------------------------------------- transportes
class _Stdio:
    """Servidor local: JSON-RPC, uma mensagem por linha, na entrada/saída do processo."""

    def __init__(self, comando: list[str], env: dict[str, str] | None = None):
        ambiente = dict(os.environ, **(env or {}))
        try:
            self.proc = subprocess.Popen(
                comando, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1, env=ambiente)
        except OSError as erro:
            raise ErroMCP(f"Não consegui iniciar {comando[0]}: {erro}") from erro
        self.respostas: dict[int, queue.Queue] = {}
        self._trava = threading.Lock()
        threading.Thread(target=self._ler, daemon=True, name="mcp-stdio").start()

    def _ler(self):
        for linha in self.proc.stdout:  # type: ignore[union-attr]
            try:
                msg = json.loads(linha)
            except ValueError:
                continue
            fila = self.respostas.get(msg.get("id")) if isinstance(msg, dict) else None
            if fila is not None:
                fila.put(msg)

    def enviar(self, msg: dict[str, Any], tempo: float) -> dict[str, Any] | None:
        fila: queue.Queue | None = None
        if "id" in msg:
            fila = queue.Queue()
            self.respostas[msg["id"]] = fila
        with self._trava:
            try:
                self.proc.stdin.write(json.dumps(msg) + "\n")  # type: ignore[union-attr]
                self.proc.stdin.flush()  # type: ignore[union-attr]
            except (OSError, ValueError) as erro:
                raise ErroMCP(f"O servidor MCP fechou: {erro}") from erro
        if fila is None:
            return None
        try:
            return fila.get(timeout=tempo)
        except queue.Empty as erro:
            raise ErroMCP("O servidor MCP não respondeu a tempo.") from erro
        finally:
            self.respostas.pop(msg["id"], None)

    def fechar(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            self.proc.kill()


class _Http:
    """Servidor remoto (Streamable HTTP): POST com JSON; resposta em JSON ou em SSE."""

    def __init__(self, url: str, token: str = ""):
        import httpx

        self.url = url
        self.sessao = ""
        self.versao = ""  # versão do protocolo negociada no initialize
        self.cabecalhos = {"Accept": "application/json, text/event-stream",
                           "Content-Type": "application/json"}
        if token:
            self.cabecalhos["Authorization"] = f"Bearer {token}"
        self.cliente = httpx.Client(timeout=60, follow_redirects=True)

    def enviar(self, msg: dict[str, Any], tempo: float) -> dict[str, Any] | None:
        import httpx

        cab = dict(self.cabecalhos)
        if self.sessao:
            cab["Mcp-Session-Id"] = self.sessao
        if self.versao:  # obrigatório depois do initialize (spec Streamable HTTP)
            cab["MCP-Protocol-Version"] = self.versao
        try:
            r = self.cliente.post(self.url, json=msg, headers=cab, timeout=tempo)
        except httpx.HTTPError as erro:
            raise ErroMCP(f"Não consegui falar com {self.url}: {erro}") from erro
        self.sessao = r.headers.get("Mcp-Session-Id", self.sessao)
        if "id" not in msg:
            return None
        if r.status_code >= 400:
            raise ErroMCP(f"Servidor MCP respondeu {r.status_code}: {r.text[:200]}")
        if "text/event-stream" in r.headers.get("Content-Type", ""):
            for linha in r.text.splitlines():
                if linha.startswith("data:"):
                    try:
                        dado = json.loads(linha[5:].strip())
                    except ValueError:
                        continue
                    if isinstance(dado, dict) and dado.get("id") == msg["id"]:
                        return dado
            raise ErroMCP("Resposta do servidor MCP sem resultado.")
        try:
            return r.json()
        except ValueError as erro:
            raise ErroMCP("Resposta do servidor MCP não é JSON.") from erro

    def fechar(self):
        self.cliente.close()


# ---------------------------------------------------------------------- servidor
class ServidorMCP:
    def __init__(self, nome: str, comando: list[str] | str | None = None, url: str = "",
                 token: str = "", env: dict[str, str] | None = None, tempo: float = 30):
        self.nome = nome
        self.tempo = tempo
        if url:
            self.transporte: _Stdio | _Http = _Http(url, token)
        elif comando:
            partes = shlex.split(comando, posix=os.name != "nt") if isinstance(comando, str) \
                else list(comando)
            self.transporte = _Stdio(partes, env)
        else:
            raise ErroMCP(f"Servidor MCP {nome!r} sem 'comando' nem 'url'.")
        self._id = 0
        self.info: dict[str, Any] = {}

    def _pedir(self, metodo: str, parametros: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        resposta = self.transporte.enviar({"jsonrpc": "2.0", "id": self._id, "method": metodo,
                                           "params": parametros or {}}, self.tempo)
        if not resposta:
            raise ErroMCP("Sem resposta do servidor MCP.")
        if resposta.get("error"):
            raise ErroMCP(resposta["error"].get("message", str(resposta["error"])))
        return resposta.get("result") or {}

    def iniciar(self) -> ServidorMCP:
        self.info = self._pedir("initialize", {"protocolVersion": VERSAO_PROTOCOLO,
                                               "capabilities": {}, "clientInfo": CLIENTE})
        if isinstance(self.transporte, _Http):
            self.transporte.versao = str(self.info.get("protocolVersion") or VERSAO_PROTOCOLO)
        self.transporte.enviar({"jsonrpc": "2.0", "method": "notifications/initialized"},
                               self.tempo)
        return self

    def ferramentas(self) -> list[dict[str, Any]]:
        saida: list[dict[str, Any]] = []
        cursor = None
        for _ in range(20):  # no máximo 20 páginas
            resultado = self._pedir("tools/list", {"cursor": cursor} if cursor else {})
            saida.extend(resultado.get("tools") or [])
            cursor = resultado.get("nextCursor")
            if not cursor:
                break
        return saida

    def chamar(self, ferramenta: str, argumentos: dict[str, Any]) -> dict[str, Any]:
        resultado = self._pedir("tools/call", {"name": ferramenta, "arguments": argumentos})
        textos = []
        for parte in resultado.get("content") or []:
            if parte.get("type") == "text":
                textos.append(parte.get("text", ""))
            elif parte.get("type") == "resource":
                textos.append(str((parte.get("resource") or {}).get("text", "")))
            else:
                textos.append(f"[{parte.get('type')}]")
        saida: dict[str, Any] = {"resultado": "\n".join(textos)[:20000]}
        if resultado.get("structuredContent") is not None:
            saida["dados"] = resultado["structuredContent"]
        if resultado.get("isError"):
            saida = {"erro": saida["resultado"] or "A ferramenta MCP falhou."}
        return saida

    def fechar(self):
        self.transporte.fechar()


# ---------------------------------------------------------------------- integração
def nome_ferramenta(servidor: str, ferramenta: str) -> str:
    limpo = re.sub(r"[^a-zA-Z0-9_]", "_", f"mcp_{servidor}_{ferramenta}")
    return limpo[:64]


_ATIVOS: dict[str, tuple[ServidorMCP, list[dict[str, Any]]]] = {}


def ferramentas_mcp(config) -> dict[str, Any]:
    """Liga os servidores [[mcp]] (uma vez) e devolve as ferramentas deles para o agente.

    Um servidor que falhar é pulado com um aviso no log: nunca impede o Optimus de abrir.
    """
    from optimus.chaves import resolver
    from optimus.tools.base import Ferramenta

    saida: dict[str, Any] = {}
    for dados in config.dados.get("mcp") or []:
        if not dados.get("ativo", True) or not dados.get("nome"):
            continue
        nome = str(dados["nome"])
        if nome not in _ATIVOS:
            try:
                servidor = ServidorMCP(nome, dados.get("comando"), dados.get("url", ""),
                                       resolver(dados.get("token", "")) or "",
                                       dados.get("env") or None).iniciar()
                _ATIVOS[nome] = (servidor, servidor.ferramentas())
            except ErroMCP as erro:
                log.warning("Servidor MCP %s não conectou: %s", nome, erro)
                continue
        servidor, lista = _ATIVOS[nome]
        risco = _RISCOS.get(str(dados.get("risco", "moderado")).lower(), MODERADO)
        for item in lista:
            esquema = item.get("inputSchema") or {}

            def executar(ctx, _s=servidor, _n=item["name"], **argumentos):
                try:
                    return _s.chamar(_n, argumentos)
                except ErroMCP as erro:
                    return {"erro": str(erro)}

            chave = nome_ferramenta(nome, item["name"])
            saida[chave] = Ferramenta(
                nome=chave, descricao=f"[{nome}] {item.get('description', '')}"[:1000],
                parametros=esquema.get("properties") or {}, funcao=executar, grupo="mcp",
                risco=risco, obrigatorios=list(esquema.get("required") or []))
    return saida


def desligar_todos() -> None:
    for servidor, _ in _ATIVOS.values():
        try:
            servidor.fechar()
        except Exception:  # noqa: BLE001
            pass
    _ATIVOS.clear()
