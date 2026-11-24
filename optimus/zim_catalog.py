"""Catálogo offline de coleções ZIM do Project NOMAD.

Os manifestos são metadados; nenhum conteúdo de terceiros é embutido no repositório.
"""
from __future__ import annotations

import json
from pathlib import Path
from optimus import zim


def caminho_catalogo() -> Path:
    return Path(__file__).with_name("catalogo") / "zim-nomad.json"


def catalogo() -> dict:
    """Retorna o catálogo versionado, anotando quais recursos já estão instalados."""
    dados = json.loads(caminho_catalogo().read_text(encoding="utf-8"))
    biblioteca = zim.pasta_biblioteca()
    instalados = set()
    try:
        instalados = {
            p.name.casefold() for p in biblioteca.iterdir()
            if p.is_file() and not p.is_symlink() and p.suffix.casefold() == ".zim"
        }
    except OSError:
        pass

    def anotar(recurso: dict) -> dict:
        url = recurso.get("url") or ""
        nome = url.rsplit("/", 1)[-1] if url else ""
        return {**recurso, "arquivo": nome or None,
                "instalado": bool(nome and nome.casefold() in instalados)}

    categorias = []
    for categoria in dados.get("categories", []):
        tiers = []
        for tier in categoria.get("tiers", []):
            tiers.append({**tier, "resources": [anotar(r) for r in tier.get("resources", [])]})
        categorias.append({**categoria, "tiers": tiers})
    wikipedia = [anotar(r) for r in dados.get("wikipedia", [])]
    return {
        "schema_version": dados.get("schema_version", 1),
        "upstream": dados.get("upstream", {}),
        "categories": categorias,
        "wikipedia": wikipedia,
        "total_recursos": sum(len(t["resources"]) for c in categorias for t in c["tiers"]) + len(wikipedia),
        "total_instalados": sum(
            sum(1 for r in t["resources"] if r["instalado"])
            for c in categorias for t in c["tiers"]
        ) + sum(1 for r in wikipedia if r["instalado"]),
    }
