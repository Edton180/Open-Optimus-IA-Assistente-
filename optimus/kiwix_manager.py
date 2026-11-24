"""Provisionamento local e isolado do Kiwix Tools.

Os binários são obtidos da distribuição oficial Kiwix por HTTPS e instalados
no diretório de dados do Optimus, sem PATH global, privilégios ou alterações
no sistema. O usuário inicia o download explicitamente pela interface.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from optimus.config import pasta_base

VERSAO = "3.8.2"
BASE_URL = "https://download.kiwix.org/release/kiwix-tools/"
MAX_DOWNLOAD = 100 * 1024 * 1024
TIMEOUT = 45


def diretorio() -> Path:
    return (pasta_base() / "tools" / "kiwix-tools").resolve()


def _pacote() -> tuple[str, str]:
    sistema = platform.system().lower()
    maquina = platform.machine().lower()
    if sistema == "windows" and maquina in ("amd64", "x86_64"):
        return f"kiwix-tools_win-x86_64-{VERSAO}.zip", "zip"
    if sistema == "linux":
        if maquina in ("x86_64", "amd64"):
            return f"kiwix-tools_linux-x86_64-{VERSAO}.tar.gz", "tar"
        if maquina in ("aarch64", "arm64"):
            return f"kiwix-tools_linux-aarch64-{VERSAO}.tar.gz", "tar"
    if sistema == "darwin":
        if maquina in ("arm64", "aarch64"):
            return f"kiwix-tools_macos-arm64-{VERSAO}.tar.gz", "tar"
        if maquina in ("x86_64", "amd64"):
            return f"kiwix-tools_macos-x86_64-{VERSAO}.tar.gz", "tar"
    raise RuntimeError(
        f"Não há pacote oficial Kiwix Tools {VERSAO} mapeado para "
        f"{platform.system()} / {platform.machine()}. Nenhum arquivo do sistema foi alterado."
    )


def executavel() -> str | None:
    raiz = diretorio() / VERSAO
    nome = "kiwix-serve.exe" if os.name == "nt" else "kiwix-serve"
    try:
        for candidato in raiz.rglob(nome):
            if candidato.is_file() and not candidato.is_symlink():
                return str(candidato)
    except OSError:
        return None
    return None


def estado() -> dict:
    caminho = executavel()
    try:
        pacote, _ = _pacote()
        suportado = True
        erro = ""
    except RuntimeError as exc:
        pacote, suportado, erro = "", False, str(exc)
    return {
        "instalado": bool(caminho),
        "gerenciado": bool(caminho),
        "versao": VERSAO if caminho else None,
        "executavel": caminho,
        "suportado": suportado,
        "pacote": pacote or None,
        "erro": erro or None,
        "origem": BASE_URL,
    }


def _baixar(url: str, destino: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Optimus-Kiwix-Manager/1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resposta:
        tamanho = int(resposta.headers.get("Content-Length") or 0)
        if tamanho > MAX_DOWNLOAD:
            raise RuntimeError("O pacote Kiwix excede o limite de download seguro (100 MB).")
        total = 0
        with destino.open("wb") as arquivo:
            while True:
                bloco = resposta.read(1024 * 1024)
                if not bloco:
                    break
                total += len(bloco)
                if total > MAX_DOWNLOAD:
                    raise RuntimeError("Download interrompido: pacote excedeu 100 MB.")
                arquivo.write(bloco)
        if tamanho and total != tamanho:
            raise RuntimeError("Download incompleto do Kiwix Tools.")


def _destino_membro(destino: Path, nome: str) -> Path:
    caminho = PurePosixPath(nome.replace("\\\\", "/"))
    if caminho.is_absolute() or ".." in caminho.parts or (caminho.parts and ":" in caminho.parts[0]):
        raise RuntimeError("Pacote Kiwix rejeitado: caminho inseguro no arquivo.")
    return destino.joinpath(*caminho.parts)


def _criar_links_seguros(destino: Path, links: list[tuple[str, str]]) -> None:
    raiz = destino.resolve()
    for nome, alvo in links:
        saida = _destino_membro(destino, nome)
        relativo = posixpath.normpath(posixpath.join(posixpath.dirname(nome), alvo))
        if relativo == ".." or relativo.startswith("../") or relativo.startswith("/"):
            raise RuntimeError("Pacote Kiwix rejeitado: link aponta para fora da pasta.")
        origem = _destino_membro(destino, relativo)
        saida.parent.mkdir(parents=True, exist_ok=True)
        if not origem.exists() or not origem.resolve().is_relative_to(raiz):
            raise RuntimeError("Pacote Kiwix rejeitado: destino de link ausente ou externo.")
        if saida.exists() or saida.is_symlink():
            continue
        try:
            os.symlink(os.path.relpath(origem, saida.parent), saida)
        except (OSError, NotImplementedError):
            if origem.is_file():
                shutil.copy2(origem, saida)
            else:
                raise RuntimeError("Este sistema não permite criar o link simbólico exigido pelo pacote Kiwix.")


def _extrair_tar(arquivo: Path, destino: Path) -> None:
    links: list[tuple[str, str]] = []
    with tarfile.open(arquivo, "r:gz") as pacote:
        membros = pacote.getmembers()
        for membro in membros:
            saida = _destino_membro(destino, membro.name)
            if membro.isdir():
                saida.mkdir(parents=True, exist_ok=True)
                continue
            if membro.issym():
                links.append((membro.name, membro.linkname))
                continue
            if membro.islnk():
                # Hardlinks são recriados como cópia segura após extrair os arquivos regulares.
                links.append((membro.name, membro.linkname))
                continue
            if not membro.isfile():
                # Não materializa dispositivos, FIFOs ou outros tipos especiais.
                continue
            saida.parent.mkdir(parents=True, exist_ok=True)
            origem = pacote.extractfile(membro)
            if origem is None:
                continue
            with origem, saida.open("wb") as f:
                shutil.copyfileobj(origem, f)
            saida.chmod(0o755 if membro.mode & 0o111 else 0o644)
    _criar_links_seguros(destino, links)


def _extrair_zip(arquivo: Path, destino: Path) -> None:
    links: list[tuple[str, str]] = []
    with zipfile.ZipFile(arquivo) as pacote:
        for membro in pacote.infolist():
            saida = _destino_membro(destino, membro.filename)
            if membro.is_dir():
                saida.mkdir(parents=True, exist_ok=True)
                continue
            modo = (membro.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(modo):
                alvo = pacote.read(membro).decode("utf-8", errors="strict")
                links.append((membro.filename, alvo))
                continue
            if stat.S_IFMT(modo) not in (0, stat.S_IFREG):
                continue
            saida.parent.mkdir(parents=True, exist_ok=True)
            with pacote.open(membro) as origem, saida.open("wb") as f:
                shutil.copyfileobj(origem, f)
            if modo & 0o111:
                saida.chmod(0o755)
    _criar_links_seguros(destino, links)


def instalar() -> dict:
    """Baixa e instala a versão oficial no diretório privado do Optimus."""
    atual = estado()
    if atual["instalado"]:
        return {**atual, "mensagem": "Kiwix Tools já está instalado pelo Optimus."}
    nome, formato = _pacote()
    raiz = diretorio()
    raiz.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kiwix-install-", dir=str(raiz)) as temporario:
        temporario = Path(temporario)
        download = temporario / nome
        extracao = temporario / "extraido"
        extracao.mkdir()
        _baixar(BASE_URL + nome, download)
        digest = hashlib.sha256(download.read_bytes()).hexdigest()
        if formato == "zip":
            _extrair_zip(download, extracao)
        else:
            _extrair_tar(download, extracao)
        binario = "kiwix-serve.exe" if os.name == "nt" else "kiwix-serve"
        candidatos = [p for p in extracao.rglob(binario) if p.is_file() and not p.is_symlink()]
        if not candidatos:
            raise RuntimeError("O pacote oficial foi baixado, mas não contém kiwix-serve.")
        versao_dir = raiz / VERSAO
        staging = raiz / (VERSAO + ".staging")
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(extracao, staging)
        destino_binario = next((p for p in staging.rglob(binario) if p.is_file()), None)
        if destino_binario is None:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError("Não foi possível preparar o executável Kiwix.")
        metadata = {
            "versao": VERSAO, "pacote": nome, "origem": BASE_URL + nome,
            "sha256_calculado": digest, "verificacao": "download via HTTPS oficial; SHA-256 calculado localmente (não é checksum assinado pelo upstream)",
        }
        (staging / "optimus-install.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        backup = raiz / (VERSAO + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if versao_dir.exists():
            versao_dir.rename(backup)
        try:
            staging.rename(versao_dir)
        except Exception:
            if backup.exists() and not versao_dir.exists():
                backup.rename(versao_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    resultado = estado()
    if not resultado["instalado"]:
        raise RuntimeError("Instalação terminou sem localizar kiwix-serve.")
    return {**resultado, "mensagem": "Kiwix Tools instalado no diretório gerenciado do Optimus."}
