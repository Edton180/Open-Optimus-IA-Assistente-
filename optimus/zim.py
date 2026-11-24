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


def importar_conteudo_inicial_nomad() -> dict:
    """Importa a mini-Wikipédia usada pelo pré-install oficial do Kiwix no Project NOMAD.

    O download é explícito, limitado ao arquivo oficial conhecido e validado pelo Git blob SHA.
    Nunca substitui arquivos existentes e só publica o arquivo após validar tamanho e integridade.
    """
    import hashlib
    import os
    import httpx

    nome = "wikipedia_en_100_mini_2026-01.zim"
    tamanho_esperado = 4_537_782
    git_blob_sha = "e56ba3c8577551a77c365425a4fc490ed7a0ca7b"
    url = (
        "https://raw.githubusercontent.com/Crosstalk-Solutions/project-nomad/"
        "main/install/wikipedia_en_100_mini_2026-01.zim"
    )
    pasta = pasta_biblioteca()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / nome
    if destino.is_file() and not destino.is_symlink():
        return {"ok": True, "ja_existia": True, "arquivo": nome,
                "tamanho_bytes": destino.stat().st_size,
                "mensagem": "A mini-Wikipédia inicial do NOMAD já está na biblioteca."}

    parcial = pasta / (nome + ".part")
    tamanho = 0
    digest = hashlib.sha1()
    try:
        with httpx.Client(follow_redirects=True,
                          timeout=httpx.Timeout(180, connect=15)) as cliente:
            with cliente.stream("GET", url, headers={"User-Agent": "Open-Optimus-ZIM/1.0"}) as resposta:
                resposta.raise_for_status()
                digest.update(f"blob {tamanho_esperado}\\0".encode("ascii"))
                with parcial.open("wb") as saida:
                    for bloco in resposta.iter_bytes(1024 * 1024):
                        if not bloco:
                            continue
                        tamanho += len(bloco)
                        if tamanho > tamanho_esperado:
                            raise RuntimeError("O arquivo recebido excede o tamanho oficial esperado.")
                        saida.write(bloco)
                        digest.update(bloco)
                    saida.flush()
                    os.fsync(saida.fileno())
        if tamanho != tamanho_esperado or digest.hexdigest() != git_blob_sha:
            raise RuntimeError(
                "A verificação de integridade da mini-Wikipédia falhou; o arquivo parcial foi descartado."
            )
        os.replace(parcial, destino)
        return {"ok": True, "ja_existia": False, "arquivo": nome,
                "tamanho_bytes": tamanho,
                "mensagem": "Mini-Wikipédia inicial do Project NOMAD adicionada e validada."}
    except Exception:
        try:
            parcial.unlink(missing_ok=True)
        except OSError:
            pass
        raise
