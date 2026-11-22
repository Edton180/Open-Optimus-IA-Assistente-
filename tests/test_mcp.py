"""Cliente MCP: servidor local por stdio e remoto por HTTP (JSON e SSE)."""

import copy
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from optimus import config as cfg
from optimus import mcp_cliente
from optimus.safety import CRITICO, MODERADO
from optimus.tools import ferramentas_ativas
from optimus.tools.base import Contexto

FALSO = str(Path(__file__).with_name("mcp_falso.py"))


@pytest.fixture(autouse=True)
def limpar():
    yield
    mcp_cliente.desligar_todos()


def _config(servidores):
    dados = copy.deepcopy(cfg.PADRAO)
    dados["mcp"] = servidores
    return cfg.Config(dados)


def test_stdio_lista_com_paginas_e_chama():
    s = mcp_cliente.ServidorMCP("falso", [sys.executable, FALSO]).iniciar()
    try:
        assert [f["name"] for f in s.ferramentas()] == ["somar", "quebrar"]
        assert s.chamar("somar", {"a": 2, "b": 3}) == {"resultado": "5", "dados": {"soma": 5}}
        assert s.chamar("quebrar", {}) == {"erro": "deu ruim"}
        with pytest.raises(mcp_cliente.ErroMCP, match="desconhecido"):
            s._pedir("nada/existe")
    finally:
        s.fechar()


def test_ferramentas_mcp_entram_no_agente_com_risco():
    config = _config([{"nome": "calc", "comando": [sys.executable, FALSO]},
                      {"nome": "perigoso", "comando": [sys.executable, FALSO],
                       "risco": "critico"}])
    ativas = ferramentas_ativas(config)
    somar = ativas["mcp_calc_somar"]
    assert somar.risco == MODERADO and somar.obrigatorios == ["a", "b"]
    assert ativas["mcp_perigoso_somar"].risco == CRITICO
    assert json.loads(somar.executar({"a": 1, "b": 1}, Contexto(config)))["resultado"] == "2"
    assert "ler_arquivo" in ativas  # as nativas continuam


def test_servidor_que_nao_abre_nao_derruba_nada():
    config = _config([{"nome": "sumiu", "comando": ["programa-que-nao-existe-xyz"]},
                      {"nome": "sem", "ativo": True}])
    assert mcp_cliente.ferramentas_mcp(config) == {}


def test_nome_da_ferramenta_seguro():
    assert mcp_cliente.nome_ferramenta("meu-app", "get.file") == "mcp_meu_app_get_file"
    assert len(mcp_cliente.nome_ferramenta("x" * 50, "y" * 50)) == 64


class _MCPHttp(BaseHTTPRequestHandler):
    sse = False

    def log_message(self, *a):
        pass

    def do_POST(self):
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "id" not in msg:
            self.send_response(202)
            self.end_headers()
            return
        assert self.headers.get("Authorization") == "Bearer tok"
        if msg["method"] == "initialize":
            res = {"protocolVersion": "x", "capabilities": {}}
        elif msg["method"] == "tools/list":
            assert self.headers.get("Mcp-Session-Id") == "sessao-1"
            res = {"tools": [{"name": "hora", "description": "Hora certa"}]}
        else:
            res = {"content": [{"type": "text", "text": "12:00"}]}
        corpo = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res})
        self.send_response(200)
        self.send_header("Mcp-Session-Id", "sessao-1")
        if _MCPHttp.sse:
            dados = f"event: message\ndata: {corpo}\n\n".encode()
            self.send_header("Content-Type", "text/event-stream")
        else:
            dados = corpo.encode()
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


@pytest.mark.parametrize("sse", [False, True])
def test_http_json_e_sse(sse):
    _MCPHttp.sse = sse
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHttp)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{servidor.server_port}/mcp"
        s = mcp_cliente.ServidorMCP("remoto", url=url, token="tok").iniciar()
        assert s.ferramentas()[0]["name"] == "hora"
        assert s.chamar("hora", {})["resultado"] == "12:00"
        s.fechar()
    finally:
        servidor.shutdown()
