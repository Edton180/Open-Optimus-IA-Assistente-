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


def _apagar_arquivo(caminho: str) -> bool:
    """Apaga o áudio/vídeo gerado, mas só se estiver numa pasta de saídas do Estúdio."""
    try:
        alvo = Path(caminho).resolve()
        permitidas = {(pasta_estudio() / "saidas").resolve(), pasta_saidas().resolve()}
        try:
            from optimus.config import carregar

            permitidas.add(pasta_saidas(carregar()).resolve())
        except Exception:  # noqa: BLE001 - sem config: só as pastas padrão
            pass
        if alvo.is_file() and any(alvo.is_relative_to(p) for p in permitidas):
            alvo.unlink()
            return True
    except OSError:
        pass
    return False


def apagar_historico(item_id: str = "", tudo: bool = False, manter_favoritos: bool = True,
                     apagar_arquivos: bool = False) -> int:
    """Remove um item (por id) ou o histórico todo. Devolve quantos itens saíram.

    `apagar_arquivos` também apaga os arquivos gerados (só dentro das pastas de saídas).
    """
    try:
        itens = json.loads(_arq_historico().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if tudo:
        sair = [i for i in itens if not (manter_favoritos and i.get("favorito"))]
    else:
        sair = [i for i in itens if item_id and i.get("id") == item_id]
    if not sair:
        return 0
    ids = {id(i) for i in sair}
    ficam = [i for i in itens if id(i) not in ids]
    if apagar_arquivos:
        for i in sair:
            _apagar_arquivo(i.get("arquivo", ""))
    _arq_historico().write_text(json.dumps(ficam, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    return len(sair)


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
