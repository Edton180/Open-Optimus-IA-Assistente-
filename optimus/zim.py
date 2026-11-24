"""Catálogo local de arquivos ZIM para conhecimento offline.

Esta etapa apenas descobre arquivos .zim na pasta gerenciada pelo Optimus.
Não baixa conteúdo, não executa kiwix-serve e não acessa diretórios externos.
"""
from __future__ import annotations

from pathlib import Path


def pasta_biblioteca() -> Path:
    """Diretório dedicado aos arquivos ZIM, dentro dos dados do Optimus."""
    from optimus.config import pasta_base

    return (pasta_base() / "biblioteca_zim").resolve()


def listar_zim() -> dict:
    """Lista arquivos ZIM regulares, sem seguir links simbólicos ou subpastas."""
    pasta = pasta_biblioteca()
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        arquivos = []
        for item in sorted(pasta.iterdir(), key=lambda p: p.name.casefold()):
            try:
                if item.is_symlink() or not item.is_file() or item.suffix.casefold() != ".zim":
                    continue
                stat = item.stat()
                arquivos.append({
                    "nome": item.name,
                    "tamanho_bytes": stat.st_size,
                    "modificado_em": int(stat.st_mtime),
                })
            except OSError:
                # Um arquivo pode desaparecer ou ficar indisponível durante a listagem.
                continue
        return {
            "total": len(arquivos),
            "tamanho_total_bytes": sum(a["tamanho_bytes"] for a in arquivos),
            "arquivos": arquivos,
            "pasta_configurada": True,
        }
    except OSError as erro:
        return {"total": 0, "tamanho_total_bytes": 0, "arquivos": [],
                "pasta_configurada": False, "erro": str(erro)}
