"""Rotas de áudio no formato da API da OpenAI, servidas pelo próprio Optimus (local).

- POST /v1/audio/speech  {"model": "...", "input": "texto", "voice": "Mordomo",
  "response_format": "mp3|wav|flac|opus", "speed": 1.0, "language": "pt-BR"}
- POST /v1/audio/transcriptions  (multipart: file, language, response_format json|text|srt|vtt)
- GET  /v1/models e /v1/audio/voices

Qualquer programa que fala com a OpenAI pode apontar para http://127.0.0.1:8765/v1.
"""

from __future__ import annotations

import json
import tempfile
from email.parser import BytesParser
from email.policy import default as politica
from pathlib import Path

_TIPOS = {"mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac", "opus": "audio/ogg",
          "aac": "audio/aac", "pcm": "audio/L16"}
# Nomes de voz da OpenAI viram vozes do Optimus (quem não conhece as nossas ainda funciona).
_VOZES_OPENAI = {"alloy": "valkyrie", "nova": "aurora", "shimmer": "lyra", "echo": "prime",
                 "onyx": "nexus", "fable": "mordomo", "ash": "titan", "coral": "valkyrie",
                 "sage": "aurora", "ballad": "mordomo", "verse": "prime"}


def _json(dados, status: int = 200) -> tuple[int, str, bytes]:
    corpo = json.dumps(dados, ensure_ascii=False).encode()
    return status, "application/json; charset=utf-8", corpo


def _erro(mensagem: str, status: int = 400):
    return _json({"error": {"message": mensagem, "type": "invalid_request_error"}}, status)


def multipart(tipo: str, corpo: bytes) -> dict[str, tuple[str, bytes]]:
    """Lê um formulário multipart: {campo: (nome do arquivo, conteúdo)}."""
    msg = BytesParser(policy=politica).parsebytes(
        f"Content-Type: {tipo}\r\nMIME-Version: 1.0\r\n\r\n".encode() + corpo)
    campos: dict[str, tuple[str, bytes]] = {}
    for parte in msg.iter_parts():
        nome = parte.get_param("name", header="content-disposition")
        if nome:
            campos[nome] = (parte.get_filename() or "", parte.get_payload(decode=True) or b"")
    return campos


def _fala(corpo: bytes, config):
    from optimus.estudio import audio, motores, vozes
    from optimus.estudio.audio import ErroEstudio

    try:
        pedido = json.loads(corpo or b"{}")
    except ValueError:
        return _erro("JSON inválido")
    texto = str(pedido.get("input") or "").strip()
    if not texto:
        return _erro("Campo 'input' vazio")
    if len(texto) > 20000:
        return _erro("Texto longo demais (máximo 20 mil caracteres)")
    formato = str(pedido.get("response_format") or "mp3").lower()
    if formato not in _TIPOS:
        return _erro(f"response_format inválido: {formato}")
    nome_voz = str(pedido.get("voice") or "")
    nome_voz = _VOZES_OPENAI.get(nome_voz.lower(), nome_voz)
    try:
        x = motores.gerar(texto, vozes.obter(nome_voz), str(pedido.get("language") or ""),
                          float(pedido.get("speed") or 1.0), config)
        if formato == "pcm":
            import numpy as np

            return 200, _TIPOS[formato], (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
        ext = {"opus": ".opus", "aac": ".m4a"}.get(formato, "." + formato)
        with tempfile.TemporaryDirectory() as pasta:
            destino = audio.salvar(x, motores.TAXA, Path(pasta) / f"fala{ext}")
            return 200, _TIPOS[formato], destino.read_bytes()
    except ErroEstudio as erro:
        return _erro(str(erro), 422)


def _transcricao(tipo: str, corpo: bytes, config):
    from optimus.estudio import legendas, transcrever
    from optimus.estudio.audio import ErroEstudio

    if "multipart/form-data" not in tipo:
        return _erro("Envie como multipart/form-data com o campo 'file'")
    campos = multipart(tipo, corpo)
    if "file" not in campos:
        return _erro("Falta o campo 'file'")
    nome, dados = campos["file"]
    idioma = campos.get("language", ("", b""))[1].decode() or ""
    formato = campos.get("response_format", ("", b"json"))[1].decode() or "json"
    sufixo = Path(nome).suffix or ".wav"
    with tempfile.TemporaryDirectory() as pasta:
        arq = Path(pasta) / f"entrada{sufixo}"
        arq.write_bytes(dados)
        try:
            trechos, falado = transcrever.transcrever(arq, idioma, config=config)
        except (ErroEstudio, ValueError) as erro:
            return _erro(str(erro), 422)
    texto = " ".join(t.texto for t in trechos)
    if formato == "text":
        return 200, "text/plain; charset=utf-8", texto.encode()
    if formato == "srt":
        return 200, "application/x-subrip; charset=utf-8", legendas.para_srt(trechos).encode()
    if formato == "vtt":
        return 200, "text/vtt; charset=utf-8", legendas.para_vtt(trechos).encode()
    saida: dict = {"text": texto}
    if formato == "verbose_json":
        saida.update(language=falado.whisper, segments=[
            {"id": i, "start": t.inicio, "end": t.fim, "text": t.texto}
            for i, t in enumerate(trechos)])
    return _json(saida)


def atender(metodo: str, caminho: str, tipo: str, corpo: bytes, config):
    caminho = caminho.rstrip("/")
    if metodo == "GET" and caminho == "/v1/models":
        return _json({"object": "list", "data": [
            {"id": "optimus-tts", "object": "model", "owned_by": "open-optimus"},
            {"id": "optimus-whisper", "object": "model", "owned_by": "open-optimus"}]})
    if metodo == "GET" and caminho == "/v1/audio/voices":
        from optimus.estudio import vozes

        return _json({"voices": [{"id": p.id, "name": p.nome, "type": p.tipo}
                                 for p in vozes.listar()]})
    if metodo == "POST" and caminho == "/v1/audio/speech":
        return _fala(corpo, config)
    if metodo == "POST" and caminho == "/v1/audio/transcriptions":
        return _transcricao(tipo, corpo, config)
    return _erro(f"Rota não encontrada: {metodo} {caminho}", 404)
