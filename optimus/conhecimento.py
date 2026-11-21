"""Base de conhecimento embutida: indexa os textos de `optimus/knowledge/*.md` no banco local.

O Optimus já vem com conhecimento geral e benigno (sobre ele mesmo, primeiros socorros,
conversões, redes, programação). Esses arquivos entram no mesmo índice FTS5 que o resto do que
ele aprende (`Banco.aprender`), então viram respostas prontas sem precisar da web nem de gastar o
modelo grande. Isso ajuda a velocidade, principalmente em PCs fracos. Veja [[base_de_conhecimento]].

A indexação é idempotente: um arquivo só é reindexado quando o conteúdo muda (comparação por
hash), e fontes embutidas de arquivos que sumiram são removidas. Assim, iniciar o Optimus várias
vezes não duplica nada nem gasta tempo à toa.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optimus.banco import Banco

PASTA_EMBUTIDA = Path(__file__).resolve().parent / "knowledge"
PREFIXO_FONTE = "embutido:"


def _titulo(texto: str, padrao: str) -> str:
    """Primeiro cabeçalho `# ...` do Markdown, ou o nome do arquivo como reserva."""
    for linha in texto.splitlines():
        achado = re.match(r"#\s+(.+)", linha.strip())
        if achado:
            return achado.group(1).strip()
    return padrao


def _assinatura(arquivos: dict[str, str]) -> dict[str, str]:
    return {nome: hashlib.sha256(texto.encode("utf-8")).hexdigest()
            for nome, texto in arquivos.items()}


def _ler_arquivos(pasta: Path) -> dict[str, str]:
    if not pasta.is_dir():
        return {}
    return {caminho.stem: caminho.read_text(encoding="utf-8")
            for caminho in sorted(pasta.glob("*.md"))}


def indexar_embutido(banco: Banco, pasta: Path | None = None,
                     estado_arq: Path | None = None) -> dict[str, int]:
    """Indexa os textos embutidos no banco, só o que mudou desde a última vez.

    Retorna um resumo {"indexados": n, "removidos": n, "total": n}. Nunca levanta erro por
    conteúdo; o chamador (app) ainda pode envolver em try/except para não travar a abertura.
    """
    pasta = pasta or PASTA_EMBUTIDA
    arquivos = _ler_arquivos(pasta)
    assinatura = _assinatura(arquivos)

    anterior: dict[str, str] = {}
    if estado_arq and estado_arq.exists():
        try:
            anterior = json.loads(estado_arq.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            anterior = {}

    indexados = 0
    for nome, texto in arquivos.items():
        if anterior.get(nome) == assinatura[nome]:
            continue  # inalterado: já está no índice
        banco.aprender(f"{PREFIXO_FONTE}{nome}", _titulo(texto, nome), texto)
        indexados += 1

    removidos = 0
    for nome in anterior:
        if nome not in arquivos:
            banco.esquecer_fonte(f"{PREFIXO_FONTE}{nome}")
            removidos += 1

    if estado_arq:
        try:
            estado_arq.parent.mkdir(parents=True, exist_ok=True)
            estado_arq.write_text(json.dumps(assinatura, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except OSError:
            pass

    return {"indexados": indexados, "removidos": removidos, "total": len(arquivos)}
