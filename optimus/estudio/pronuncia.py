"""Dicionário de pronúncia: "escreve assim, fala assim", aplicado antes de gerar a voz.

Ex.: "Optimus" → "Óptimus", "SQL" → "ésse quê éle", "Kaik" → "Káique". Vale para todas as
vozes, inclusive as clonadas. Fica em `estudio/pronuncia.json`, fácil de editar e compartilhar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from optimus.config import pasta_base


def _arquivo() -> Path:
    return pasta_base() / "estudio" / "pronuncia.json"


def listar() -> list[dict]:
    try:
        dados = json.loads(_arquivo().read_text(encoding="utf-8"))
        return [d for d in dados if d.get("escrito") and d.get("falado")]
    except (OSError, ValueError):
        return []


def _gravar(regras: list[dict]) -> None:
    arq = _arquivo()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(regras, ensure_ascii=False, indent=1), encoding="utf-8")


def adicionar(escrito: str, falado: str, idioma: str = "") -> dict:
    escrito, falado = escrito.strip(), falado.strip()
    if not escrito or not falado:
        raise ValueError("Diga como se escreve e como se fala.")
    regras = [r for r in listar() if r["escrito"].lower() != escrito.lower()
              or r.get("idioma", "") != idioma]
    regra = {"escrito": escrito, "falado": falado, "idioma": idioma}
    regras.append(regra)
    _gravar(regras)
    return regra


def remover(escrito: str) -> bool:
    regras = listar()
    novas = [r for r in regras if r["escrito"].lower() != escrito.strip().lower()]
    _gravar(novas)
    return len(novas) != len(regras)


def aplicar(texto: str, idioma: str = "", regras: list[dict] | None = None) -> str:
    """Troca cada palavra inteira (sem diferenciar maiúsculas). Regras mais longas primeiro,
    para "São Paulo FC" ganhar de "São Paulo"."""
    regras = listar() if regras is None else regras
    validas = [r for r in regras if not r.get("idioma") or not idioma
               or idioma.lower().startswith(r["idioma"].lower())]
    for r in sorted(validas, key=lambda r: len(r["escrito"]), reverse=True):
        padrao = rf"(?<!\w){re.escape(r['escrito'])}(?!\w)"
        texto = re.sub(padrao, lambda _m, f=r["falado"]: f, texto, flags=re.IGNORECASE)
    return texto


def exportar(destino: str | Path) -> Path:
    destino = Path(destino)
    destino.write_text(json.dumps(listar(), ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def importar(origem: str | Path) -> int:
    """Aceita o JSON exportado ou um texto com uma regra por linha: `escrito = falado`."""
    conteudo = Path(origem).read_text(encoding="utf-8-sig")
    try:
        novas = [r for r in json.loads(conteudo) if isinstance(r, dict)]
    except ValueError:
        novas = []
        for linha in conteudo.splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                a, b = linha.split("=", 1)
                novas.append({"escrito": a.strip(), "falado": b.strip()})
    for r in novas:
        adicionar(r.get("escrito", ""), r.get("falado", ""), r.get("idioma", ""))
    return len(novas)
