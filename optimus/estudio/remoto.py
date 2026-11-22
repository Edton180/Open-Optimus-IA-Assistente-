"""Servidor de voz remoto: usa qualquer servidor compatível com a API de áudio da OpenAI
(`/v1/audio/speech` e `/v1/audio/transcriptions`) como motor do estúdio.

Serve para rodar os modelos pesados em outra máquina com placa de vídeo (outro PC da casa,
um servidor na nuvem, outro Optimus com `optimus web`) e usar daqui como se fosse local.

Configuração (`config.toml`):

    [estudio]
    servidor_voz_url = "http://pc-da-sala:8765/v1"
    servidor_voz_chave = "cofre:estudio.servidor_voz_chave"   # opcional
    servidor_voz_modelo = "tts-1"
    servidor_voz_transcricao = "whisper-1"
    servidor_voz_voz = "alloy"
"""

from __future__ import annotations

from pathlib import Path

from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho


def _ajustes(config) -> dict:
    if config is None:
        return {}
    return {"url": config.get("estudio", "servidor_voz_url", ""),
            "chave": config.get("estudio", "servidor_voz_chave", ""),
            "modelo_voz": config.get("estudio", "servidor_voz_modelo", ""),
            "modelo_transcricao": config.get("estudio", "servidor_voz_transcricao", ""),
            "voz": config.get("estudio", "servidor_voz_voz", "")}


def configurado(config) -> bool:
    return bool(_ajustes(config).get("url"))


def _base(config) -> tuple[str, dict]:
    dados = _ajustes(config)
    url = str(dados.get("url") or "").rstrip("/")
    if not url:
        raise ErroEstudio("Configure o servidor de voz: optimus config estudio.servidor_voz_url "
                          "http://maquina:porta/v1")
    if not url.endswith("/v1"):
        url += "/v1"
    cabecalhos = {}
    chave = dados.get("chave") or ""  # config.get já resolve "cofre:"
    if chave:
        cabecalhos["Authorization"] = f"Bearer {chave}"
    return url, cabecalhos


def falar(texto: str, voz: str = "", velocidade: float = 1.0, idioma: str = "",
          config=None):
    """Texto → (numpy float32, taxa)."""
    import httpx

    from optimus.estudio.motores import _decodificar

    url, cabecalhos = _base(config)
    dados = _ajustes(config)
    corpo = {"model": dados.get("modelo_voz") or "tts-1", "input": texto,
             "voice": voz or dados.get("voz") or "alloy", "response_format": "wav",
             "speed": float(velocidade or 1.0)}
    if idioma:
        corpo["language"] = idioma
    try:
        r = httpx.post(f"{url}/audio/speech", headers=cabecalhos, json=corpo, timeout=600)
        r.raise_for_status()
    except httpx.HTTPError as erro:
        raise ErroEstudio(f"O servidor de voz não respondeu: {erro}") from erro
    tipo = r.headers.get("content-type", "")
    formato = "mp3" if "mpeg" in tipo or "mp3" in tipo else "wav"
    return _decodificar(r.content, formato), 24000


def transcrever(caminho: str | Path, idioma: str = "", config=None) -> tuple[list[Trecho], str]:
    import httpx

    url, cabecalhos = _base(config)
    dados = _ajustes(config)
    campos = {"model": dados.get("modelo_transcricao") or "whisper-1",
              "response_format": "verbose_json", "timestamp_granularities[]": "segment"}
    if idioma:
        campos["language"] = idioma.split("-")[0]
    try:
        with open(caminho, "rb") as f:
            r = httpx.post(f"{url}/audio/transcriptions", headers=cabecalhos, data=campos,
                           files={"file": (Path(caminho).name, f)}, timeout=3600)
        r.raise_for_status()
        resposta = r.json()
    except (httpx.HTTPError, ValueError) as erro:
        raise ErroEstudio(f"O servidor de transcrição falhou: {erro}") from erro
    trechos = [Trecho(float(s.get("start", 0)), float(s.get("end", 0)),
                      str(s.get("text", "")).strip())
               for s in resposta.get("segments") or [] if str(s.get("text", "")).strip()]
    if not trechos and resposta.get("text"):
        trechos = [Trecho(0.0, float(resposta.get("duration") or 0), resposta["text"].strip())]
    return trechos, str(resposta.get("language") or "")
