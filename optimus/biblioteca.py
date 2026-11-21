"""Biblioteca de documentos: indexa uma pasta inteira de arquivos no conhecimento local.

O Optimus já aprende de um link, arquivo ou texto avulso (`tools/memoria.aprender`). Aqui ele
aponta para uma **pasta** de documentos (relatórios, manuais, anotações, PDFs) e indexa todos no
banco FTS5, para responder sobre eles offline, sem mandar nada para fora. É o "converse com os
seus documentos" rodando 100% no seu PC.

A indexação é idempotente (igual à base embutida, veja [[conhecimento]]): guarda um hash de cada
arquivo e só reindexa o que mudou; arquivos removidos da pasta saem do índice. As fontes ficam
com o prefixo `biblioteca:` para separá-las do que foi aprendido de outras formas.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optimus.banco import Banco

PREFIXO = "biblioteca:"
# Extensões de texto que lemos direto. PDF é tratado à parte (pypdf, opcional).
EXT_TEXTO = {".txt", ".text", ".md", ".markdown", ".rst", ".csv", ".tsv", ".log", ".json",
             ".yaml", ".yml", ".ini", ".cfg", ".html", ".htm"}
EXT_PDF = {".pdf"}
EXTENSOES = EXT_TEXTO | EXT_PDF


def _ler_pdf(caminho: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(caminho)).pages)
    except Exception:  # noqa: BLE001
        return ""


def _ler(caminho: Path) -> str:
    if caminho.suffix.lower() in EXT_PDF:
        return _ler_pdf(caminho)
    try:
        return caminho.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _arquivos(pasta: Path, recursivo: bool) -> list[Path]:
    if not pasta.is_dir():
        return []
    passo = pasta.rglob("*") if recursivo else pasta.glob("*")
    return sorted(c for c in passo if c.is_file() and c.suffix.lower() in EXTENSOES)


def _estado_padrao() -> Path:
    from optimus.config import pasta_base

    return pasta_base() / "biblioteca.json"


def _carregar_estado(arq: Path) -> dict[str, str]:
    if arq and arq.exists():
        try:
            return json.loads(arq.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def indexar_pasta(banco: Banco, pasta: Path, recursivo: bool = True,
                  estado_arq: Path | None = None) -> dict:
    """Indexa (ou atualiza) todos os documentos de uma pasta no conhecimento local.

    Só reindexa arquivos novos ou alterados; remove do índice os que sumiram da pasta. Devolve
    um resumo {"indexados", "removidos", "trechos", "ignorados", "total"}.
    """
    pasta = Path(pasta).expanduser().resolve()
    estado_arq = estado_arq or _estado_padrao()
    estado = _carregar_estado(estado_arq)

    arquivos = _arquivos(pasta, recursivo)
    desta_pasta = {k for k in estado if k.startswith(f"{pasta}/") or k == str(pasta)}
    vistos: set[str] = set()

    indexados = trechos = ignorados = 0
    for caminho in arquivos:
        chave = str(caminho)
        vistos.add(chave)
        conteudo = _ler(caminho)
        if not conteudo.strip():
            ignorados += 1  # vazio ou PDF sem pypdf/sem texto extraível
            continue
        assinatura = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
        if estado.get(chave) == assinatura:
            continue
        trechos += banco.aprender(f"{PREFIXO}{caminho}", caminho.name, conteudo)
        estado[chave] = assinatura
        indexados += 1

    removidos = 0
    for chave in desta_pasta - vistos:
        banco.esquecer_fonte(f"{PREFIXO}{chave}")
        estado.pop(chave, None)
        removidos += 1

    try:
        estado_arq.parent.mkdir(parents=True, exist_ok=True)
        estado_arq.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass

    return {"indexados": indexados, "removidos": removidos, "trechos": trechos,
            "ignorados": ignorados, "total": len(arquivos), "pasta": str(pasta)}


def fontes(banco: Banco) -> list[dict]:
    """Documentos já indexados pela biblioteca (fontes com o prefixo `biblioteca:`)."""
    return [f for f in banco.fontes() if str(f.get("fonte", "")).startswith(PREFIXO)]


def esquecer_pasta(banco: Banco, pasta: Path, estado_arq: Path | None = None) -> int:
    """Remove do índice todos os documentos de uma pasta. Devolve quantas fontes saíram."""
    pasta = Path(pasta).expanduser().resolve()
    estado_arq = estado_arq or _estado_padrao()
    estado = _carregar_estado(estado_arq)
    alvo = f"{PREFIXO}{pasta}/"
    removidos = 0
    for f in fontes(banco):
        nome = str(f["fonte"])
        if nome.startswith(alvo) or nome == f"{PREFIXO}{pasta}":
            banco.esquecer_fonte(nome)
            estado.pop(nome[len(PREFIXO):], None)
            removidos += 1
    try:
        estado_arq.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return removidos
