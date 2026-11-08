"""Servidor HTTP que fala o protocolo do Ollama (/api/chat em streaming, /api/tags...).

Não é um mock do código do Optimus: o Optimus conversa com ele pela rede, exatamente
como com o Ollama de verdade. Serve para testar o adaptador, o streaming, as ferramentas
e a interface sem baixar um modelo de vários GB. Também dá para rodar à mão:

    python tests/ollama_falso.py 11500
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Manipulador(BaseHTTPRequestHandler):
    pedidos: list[dict] = []
    atraso = 0.01

    def log_message(self, *args):
        pass

    def _json(self, dados, status=200):
        corpo = json.dumps(dados).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/api/version":
            return self._json({"version": "0.0-falso"})
        if self.path == "/api/tags":
            return self._json({"models": [{"name": "qwen3.5:2b"}, {"name": "gemma3:1b"}]})
        self._json({"error": "não achei"}, 404)

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        Manipulador.pedidos.append(corpo)
        if self.path != "/api/chat":
            return self._json({"status": "success"})
        mensagens = corpo.get("messages", [])
        ultima = mensagens[-1] if mensagens else {}
        ferramentas = {f["function"]["name"] for f in corpo.get("tools") or []}
        texto = (ultima.get("content") or "").lower()
        chamada = None
        if ultima.get("role") == "tool":
            resposta = "Feito. " + ("Não apaguei, você negou." if "não autorizou" in texto
                                    else "Resultado conferido: tudo certo.")
        elif "apague" in texto and "apagar" in ferramentas:
            caminho = texto.split("apague", 1)[1].strip() or "~/teste.txt"
            chamada = {"function": {"name": "apagar", "arguments": {"caminho": caminho}}}
            resposta = ""
        elif "[resultado de" in texto:
            resposta = "Segundo a pesquisa, encontrei os resultados acima. Primeira frase. " \
                       "Segunda frase com mais detalhes. Terceira frase final."
        else:
            resposta = ("Olá! Sou o Optimus rodando com um modelo local. Esta é uma resposta "
                        "longa, com várias frases, para testar o streaming. Cada frase deve "
                        "ser falada inteira. E esta é a última frase da resposta.")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for palavra in resposta.split(" ") if resposta else []:
            pacote = {"message": {"role": "assistant", "content": palavra + " "}, "done": False}
            self.wfile.write((json.dumps(pacote) + "\n").encode())
            self.wfile.flush()
            time.sleep(Manipulador.atraso)
        if chamada:
            pacote = {"message": {"role": "assistant", "content": "", "tool_calls": [chamada]},
                      "done": False}
            self.wfile.write((json.dumps(pacote) + "\n").encode())
        fim = {"message": {"role": "assistant", "content": ""}, "done": True,
               "eval_count": 40, "eval_duration": 2_000_000_000}
        self.wfile.write((json.dumps(fim) + "\n").encode())


def iniciar(porta: int = 0) -> tuple[ThreadingHTTPServer, str]:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}"


if __name__ == "__main__":
    Manipulador.atraso = 0.06
    _, url = iniciar(int(sys.argv[1]) if len(sys.argv) > 1 else 11500)
    print("Ollama falso em", url)
    while True:
        time.sleep(3600)
