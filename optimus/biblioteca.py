"""Biblioteca local de documentos, incremental e segura.

Indexa pastas no SQLite FTS5 existente. Os originais nunca são alterados nem enviados
para serviços externos. O estado por hash evita reprocessamento; erros de leitura não
apagam conteúdo previamente indexado.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optimus.banco import Banco

PREFIXO = "biblioteca:"
EXT_TEXTO = {
    ".txt", ".text", ".md", ".markdown", ".rst", ".csv", ".tsv", ".log",
    ".json", ".yaml", ".yml", ".ini", ".cfg", ".html", ".htm",
}
EXT_PDF = {".pdf"}
EXT_DOCX = {".docx"}
EXTENSOES = EXT_TEXTO | EXT_PDF | EXT_DOCX
MAX_BYTES = 32 * 1024 * 1024


def _ler_pdf(caminho: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as erro:
        raise RuntimeError("Dependência ausente: instale 'optimus-assistente[documentos]'.") from erro
    leitor = PdfReader(str(caminho))
    paginas = []
    for numero, pagina in enumerate(leitor.pages, 1):
        texto = (pagina.extract_text() or "").strip()
        if texto:
            paginas.append(f"[Página {numero}]\n{texto}")
    return "\n\n".join(paginas)


def _ler_docx(caminho: Path) -> str:
    try:
        from docx import Document
    except ImportError as erro:
        raise RuntimeError("Dependência ausente: instale 'optimus-assistente[documentos]'.") from erro
    documento = Document(str(caminho))
    partes = [p.text.strip() for p in documento.paragraphs if p.text.strip()]
    for tabela in documento.tables:
        for linha in tabela.rows:
            celulas = [celula.text.strip().replace("\n", " ") for celula in linha.cells]
            if any(celulas):
                partes.append(" | ".join(celulas))
    return "\n".join(partes)


def _ler(caminho: Path) -> str:
    tamanho = caminho.stat().st_size
    if tamanho > MAX_BYTES:
        raise ValueError(f"Arquivo excede o limite de {MAX_BYTES // (1024 * 1024)} MiB.")
    extensao = caminho.suffix.lower()
    if extensao == ".pdf":
        return _ler_pdf(caminho)
    if extensao == ".docx":
        return _ler_docx(caminho)
    return caminho.read_text(encoding="utf-8", errors="replace")


def _arquivos(pasta: Path, recursivo: bool) -> list[Path]:
    if not pasta.is_dir():
        return []
    passo = pasta.rglob("*") if recursivo else pasta.glob("*")
    # Não seguir links simbólicos: uma pasta da biblioteca não deve indexar arquivos externos
    # por acidente ao conter um atalho/symlink.
    return sorted(c for c in passo if c.is_file() and not c.is_symlink()
                  and c.suffix.lower() in EXTENSOES)


def _estado_padrao() -> Path:
    from optimus.config import pasta_base
    return pasta_base() / "biblioteca.json"


def _sob_pasta(caminho: str, pasta: Path) -> bool:
    try:
        return Path(caminho).resolve() == pasta or Path(caminho).resolve().is_relative_to(pasta)
    except (OSError, ValueError):
        return False


def _carregar_estado(arq: Path) -> dict[str, str]:
    if arq and arq.exists():
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def indexar_pasta(banco: Banco, pasta: Path, recursivo: bool = True,
                  estado_arq: Path | None = None) -> dict:
    """Indexa/atualiza documentos; remove do índice somente arquivos realmente removidos.

    Uma pasta inexistente gera FileNotFoundError e jamais é interpretada como pasta vazia.
    Erros de leitura e limites excedidos preservam a versão já indexada.
    """
    pasta = Path(pasta).expanduser().resolve()
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada ou inacessível: {pasta}")
    estado_arq = estado_arq or _estado_padrao()
    estado = _carregar_estado(estado_arq)
    arquivos = _arquivos(pasta, recursivo)
    desta_pasta = {k for k in estado if _sob_pasta(k, pasta)}
    vistos: set[str] = set()
    indexados = trechos = ignorados = 0
    erros: list[dict[str, str]] = []

    for caminho in arquivos:
        chave = str(caminho)
        vistos.add(chave)
        try:
            conteudo = _ler(caminho)
        except (OSError, ValueError, RuntimeError) as erro:
            erros.append({"arquivo": caminho.name, "erro": str(erro)})
            continue
        if not conteudo.strip():
            ignorados += 1
            if chave in estado:
                banco.esquecer_fonte(f"{PREFIXO}{caminho}")
                estado.pop(chave, None)
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
    except OSError as erro:
        erros.append({"arquivo": str(estado_arq), "erro": f"Não foi possível salvar o estado: {erro}"})

    return {"indexados": indexados, "removidos": removidos, "trechos": trechos,
            "ignorados": ignorados, "total": len(arquivos), "erros": erros,
            "pasta": str(pasta)}


def fontes(banco: Banco) -> list[dict]:
    return [f for f in banco.fontes() if str(f.get("fonte", "")).startswith(PREFIXO)]


def esquecer_pasta(banco: Banco, pasta: Path, estado_arq: Path | None = None) -> int:
    # Esquecer é uma ação explícita: deve funcionar mesmo se o disco/pasta foi removido.
    # A proteção contra pastas ausentes pertence à indexação, não à remoção solicitada.
    pasta = Path(pasta).expanduser().resolve()
    estado_arq = estado_arq or _estado_padrao()
    estado = _carregar_estado(estado_arq)
    removidos = 0
    for fonte in fontes(banco):
        nome = str(fonte["fonte"])
        caminho = nome[len(PREFIXO):]
        if _sob_pasta(caminho, pasta):
            banco.esquecer_fonte(nome)
            estado.pop(caminho, None)
            removidos += 1
    try:
        estado_arq.parent.mkdir(parents=True, exist_ok=True)
        estado_arq.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return removidos
