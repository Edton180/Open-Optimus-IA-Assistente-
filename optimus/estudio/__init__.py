"""Estúdio de voz do Open Optimus: gerar e clonar vozes (português do Brasil em primeiro
lugar), transcrever, legendar, traduzir e dublar vídeos, tudo no seu PC.

Módulos: `vozes` (perfis), `motores` (geração), `transcrever`, `traduzir`, `legendas`,
`dublagem`, `fila` (tarefas longas), `pronuncia`, `audio` (ffmpeg) e `idiomas`.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from optimus.config import pasta_base


def pasta_estudio() -> Path:
    return pasta_base() / "estudio"


def pasta_saidas(config=None) -> Path:
    escolhida = config.get("estudio", "pasta_saidas", "") if config is not None else ""
    pasta = Path(escolhida).expanduser() if escolhida else pasta_estudio() / "saidas"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


# ---------------------------------------------------------------------- histórico
def _arq_historico() -> Path:
    return pasta_estudio() / "historico.json"


def historico(busca: str = "", so_favoritos: bool = False, limite: int = 200) -> list[dict]:
    try:
        itens = json.loads(_arq_historico().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        itens = []
    if busca:
        b = busca.lower()
        itens = [i for i in itens if b in (i.get("texto", "") + i.get("voz", "")).lower()]
    if so_favoritos:
        itens = [i for i in itens if i.get("favorito")]
    return itens[-limite:][::-1]


def registrar(tipo: str, arquivo: str | Path, texto: str = "", voz: str = "",
              idioma: str = "") -> dict:
    try:
        itens = json.loads(_arq_historico().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        itens = []
    item = {"id": uuid.uuid4().hex[:10], "tipo": tipo, "arquivo": str(arquivo),
            "texto": texto[:300], "voz": voz, "idioma": idioma,
            "quando": time.strftime("%Y-%m-%d %H:%M"), "favorito": False}
    itens = (itens + [item])[-1000:]
    _arq_historico().parent.mkdir(parents=True, exist_ok=True)
    _arq_historico().write_text(json.dumps(itens, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    return item


def favoritar(item_id: str, favorito: bool = True) -> bool:
    try:
        itens = json.loads(_arq_historico().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    achou = False
    for i in itens:
        if i.get("id") == item_id:
            i["favorito"], achou = bool(favorito), True
    _arq_historico().write_text(json.dumps(itens, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    return achou
