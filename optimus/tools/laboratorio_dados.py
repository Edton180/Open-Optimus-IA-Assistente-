"""Laboratório de dados local: transformações seguras sem executar código recebido.

Operações deliberadamente limitadas a codificação, decodificação, hash e compressão.
Não avalia scripts, expressões, shell ou payloads.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import html
import urllib.parse
import zlib

from optimus.tools.base import ferramenta, texto
from optimus.safety import LIVRE


_OPERACOES = ("base64_codificar", "base64_decodificar", "url_codificar",
              "url_decodificar", "html_escapar", "html_desescapar",
              "hex_codificar", "hex_decodificar", "sha256", "sha512",
              "md5", "gzip_comprimir", "gzip_descomprimir")


@ferramenta(
    "laboratorio_dados",
    "Laboratório local estilo CyberChef: codifica/decodifica Base64, URL, HTML e hexadecimal; "
    "calcula SHA-256/SHA-512/MD5 e comprime/descomprime gzip. Nunca executa o conteúdo.",
    {"operacao": {"type": "string", "enum": list(_OPERACOES),
                  "description": "Transformação a executar"},
     "texto": texto("Texto de entrada. Para gzip descomprimir, use Base64 do arquivo gzip.")},
    grupo="geral", risco=LIVRE, obrigatorios=["operacao", "texto"],
)
def laboratorio_dados(ctx, operacao: str, texto: str):
    if operacao not in _OPERACOES:
        return {"erro": "Operação não suportada.", "operacoes": list(_OPERACOES)}
    bruto = str(texto).encode("utf-8")
    if len(bruto) > 2 * 1024 * 1024:
        return {"erro": "Limite de entrada: 2 MiB."}
    try:
        if operacao == "base64_codificar":
            resultado = base64.b64encode(bruto).decode("ascii")
        elif operacao == "base64_decodificar":
            resultado = base64.b64decode(texto, validate=True).decode("utf-8")
        elif operacao == "url_codificar":
            resultado = urllib.parse.quote(texto, safe="")
        elif operacao == "url_decodificar":
            resultado = urllib.parse.unquote(texto, errors="strict")
        elif operacao == "html_escapar":
            resultado = html.escape(texto)
        elif operacao == "html_desescapar":
            resultado = html.unescape(texto)
        elif operacao == "hex_codificar":
            resultado = bruto.hex()
        elif operacao == "hex_decodificar":
            resultado = bytes.fromhex(texto).decode("utf-8")
        elif operacao in ("sha256", "sha512", "md5"):
            resultado = hashlib.new(operacao, bruto).hexdigest()
        elif operacao == "gzip_comprimir":
            resultado = base64.b64encode(gzip.compress(bruto)).decode("ascii")
        else:
            comprimido = base64.b64decode(texto, validate=True)
            if len(comprimido) > 2 * 1024 * 1024:
                return {"erro": "Limite do arquivo comprimido: 2 MiB."}
            descompactador = zlib.decompressobj(16 + zlib.MAX_WBITS)
            descomprimido = descompactador.decompress(comprimido, 8 * 1024 * 1024 + 1)
            if len(descomprimido) > 8 * 1024 * 1024 or descompactador.unconsumed_tail:
                return {"erro": "O conteúdo descomprimido excede 8 MiB."}
            descomprimido += descompactador.flush()
            if not descompactador.eof:
                raise ValueError("Fluxo gzip incompleto ou truncado.")
            if len(descomprimido) > 8 * 1024 * 1024:
                return {"erro": "O conteúdo descomprimido excede 8 MiB."}
            resultado = descomprimido.decode("utf-8")
    except (ValueError, UnicodeError, OSError) as erro:
        return {"erro": f"Não foi possível executar {operacao}: {erro}"}
    return {"operacao": operacao, "resultado": resultado, "local": True}
