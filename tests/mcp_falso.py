"""Servidor MCP mínimo (stdio) para os testes: uma ferramenta "somar" e uma que falha."""

import json
import sys

FERRAMENTAS = [
    {"name": "somar", "description": "Soma dois números",
     "inputSchema": {"type": "object", "properties": {"a": {"type": "number"},
                                                      "b": {"type": "number"}},
                     "required": ["a", "b"]}},
    {"name": "quebrar", "description": "Sempre falha", "inputSchema": {"type": "object"}},
]

for linha in sys.stdin:
    msg = json.loads(linha)
    if "id" not in msg:
        continue
    metodo, p = msg.get("method"), msg.get("params") or {}
    if metodo == "initialize":
        resultado = {"protocolVersion": p.get("protocolVersion"), "capabilities": {"tools": {}},
                     "serverInfo": {"name": "falso", "version": "1"}}
    elif metodo == "tools/list":
        if p.get("cursor") == "pag2":
            resultado = {"tools": FERRAMENTAS[1:]}
        else:
            resultado = {"tools": FERRAMENTAS[:1], "nextCursor": "pag2"}
    elif metodo == "tools/call" and p["name"] == "somar":
        a, b = p["arguments"]["a"], p["arguments"]["b"]
        resultado = {"content": [{"type": "text", "text": str(a + b)}],
                     "structuredContent": {"soma": a + b}}
    elif metodo == "tools/call":
        resultado = {"content": [{"type": "text", "text": "deu ruim"}], "isError": True}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                          "error": {"code": -32601, "message": "método desconhecido"}}),
              flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": resultado}), flush=True)
