"""Integração Kiwix isolada, com instalação gerenciada e busca ZIM local.

O Optimus só encerra processos Popen que criou nesta instância. Nunca tenta
localizar ou matar processos Kiwix de terceiros.
"""
from __future__ import annotations

import atexit
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from optimus import zim, kiwix_manager

HOST = "127.0.0.1"
PORT = 8767
_lock = threading.RLock()
_processo: subprocess.Popen | None = None
_arquivo_ativo: str | None = None
_porta_ativa = PORT


def _executavel() -> str | None:
    """Prefere a instalação privada do Optimus; PATH é fallback compatível."""
    return kiwix_manager.executavel() or shutil.which("kiwix-serve")


def _porta_disponivel() -> int:
    """Prefere a porta padrão, mas usa porta efêmera sem tocar em serviços externos."""
    for porta in (PORT, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, porta))
                return int(sock.getsockname()[1])
            except OSError:
                continue
    raise RuntimeError("Não foi possível reservar uma porta local para o leitor Kiwix.")


def _zim_name(nome: str) -> str:
    """Reproduz a normalização oficial de ZIM name usada pelo kiwix-serve."""
    base = Path(nome).stem.lower()
    base = "".join(c for c in unicodedata.normalize("NFKD", base)
                   if not unicodedata.combining(c))
    return base.replace(" ", "_").replace("+", "plus")


def _arquivo_seguro(nome: str) -> Path:
    if not isinstance(nome, str) or not nome or Path(nome).name != nome:
        raise ValueError("Selecione um arquivo ZIM válido da biblioteca.")
    if not nome.casefold().endswith(".zim"):
        raise ValueError("O arquivo selecionado precisa ter extensão .zim.")
    pasta = zim.pasta_biblioteca()
    alvo = pasta / nome
    if alvo.is_symlink() or not alvo.is_file() or alvo.resolve().parent != pasta.resolve():
        raise ValueError("O arquivo ZIM não existe na biblioteca gerenciada.")
    return alvo.resolve()


def estado() -> dict:
    global _processo, _arquivo_ativo
    with _lock:
        if _processo is not None and _processo.poll() is not None:
            _processo = None
            _arquivo_ativo = None
        ativo = _processo is not None
        instalacao = kiwix_manager.estado()
        executavel = _executavel()
        return {
            **instalacao,
            "instalado": bool(executavel),
            "executavel_disponivel": bool(executavel),
            "origem_instalacao": "optimus" if instalacao["instalado"] else
                ("sistema" if executavel else None),
            "executando": ativo,
            "arquivo": _arquivo_ativo if ativo else None,
            "url": f"http://{HOST}:{_porta_ativa}/" if ativo else None,
            "host": HOST,
            "porta": _porta_ativa if ativo else PORT,
        }


def instalar() -> dict:
    return kiwix_manager.instalar()


def iniciar(nome: str) -> dict:
    """Inicia kiwix-serve somente para um ZIM gerenciado, sob demanda."""
    global _processo, _arquivo_ativo, _porta_ativa
    alvo = _arquivo_seguro(nome)
    with _lock:
        if _processo is not None and _processo.poll() is None:
            if _arquivo_ativo == alvo.name:
                return estado()
            raise RuntimeError("O leitor Kiwix já está aberto com outro arquivo. Feche-o antes.")
        _processo = None
        _arquivo_ativo = None
        executavel = _executavel()
        if not executavel:
            raise FileNotFoundError(
                "Kiwix Tools não está instalado. Use 'Instalar Kiwix automaticamente' nesta tela."
            )
        kwargs = {
            "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL, "shell": False, "close_fds": True,
        }
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        _porta_ativa = _porta_disponivel()
        _processo = subprocess.Popen(
            [executavel, f"--address={HOST}", f"--port={_porta_ativa}", str(alvo)],
            **kwargs,
        )
        _arquivo_ativo = alvo.name
        time.sleep(0.35)
        if _processo.poll() is not None:
            _processo = None
            _arquivo_ativo = None
            raise RuntimeError(
                "O Kiwix não iniciou. A porta padrão pode estar ocupada por outro serviço; "
                "nenhum processo externo foi encerrado."
            )
        return estado()


def _xml_resultados(xml: bytes, nome_zim: str) -> list[dict]:
    raiz = ET.fromstring(xml)
    itens = []
    for item in raiz.iter():
        if item.tag.rsplit("}", 1)[-1].lower() not in ("item", "entry"):
            continue
        campos = {}
        for filho in item.iter():
            chave = filho.tag.rsplit("}", 1)[-1].lower()
            if chave in ("title", "link", "description", "content", "url") and chave not in campos:
                campos[chave] = (filho.attrib.get("href") or filho.text or "").strip()
        titulo = campos.get("title", "")
        link = campos.get("link") or campos.get("url", "")
        trecho = campos.get("description") or campos.get("content", "")
        if not titulo or not link:
            continue
        if link.startswith("/"):
            url = f"http://{HOST}:{_porta_ativa}" + link
        else:
            partes = urlsplit(link)
            if partes.scheme not in ("http", "https") or partes.hostname not in ("127.0.0.1", "localhost"):
                # Não transforma URLs externas encontradas em conteúdo ZIM em links confiáveis.
                continue
            if partes.port not in (None, _porta_ativa):
                continue
            url = f"http://{HOST}:{_porta_ativa}" + (partes.path or "/")
            if partes.query:
                url += "?" + partes.query
            if partes.fragment:
                url += "#" + partes.fragment
        itens.append({
            "titulo": titulo[:500], "trecho": trecho[:2000],
            "arquivo_zim": nome_zim, "url": url,
            "citacao": f"{nome_zim} · {titulo}",
            "tipo_fonte": "ZIM",
        })
    return itens


def buscar(termo: str, nome: str = "", limite: int = 10) -> dict:
    """Busca no índice textual interno do ZIM via endpoint público do Kiwix.

    O servidor é iniciado temporariamente pelo Optimus quando necessário e
    somente o processo criado nesta instância pode ser encerrado.
    """
    termo = str(termo or "").strip()
    if len(termo) < 2 or len(termo) > 300:
        raise ValueError("Informe uma busca entre 2 e 300 caracteres.")
    arquivos = zim.listar_zim().get("arquivos", [])
    if nome:
        arquivos = [a for a in arquivos if a["nome"] == nome]
    if not arquivos:
        return {"consulta": termo, "resultados": [], "total": 0,
                "aviso": "Nenhum arquivo ZIM disponível para pesquisar."}
    limite = max(1, min(int(limite), 30))
    resultados = []
    erros = []
    for arquivo in arquivos[:20]:
        nome_arquivo = arquivo["nome"]
        iniciou_aqui = False
        with _lock:
            processo_ativo = _processo is not None and _processo.poll() is None
            ativo_nome = _arquivo_ativo
        if processo_ativo and ativo_nome != nome_arquivo:
            erros.append(f"{nome_arquivo}: feche o leitor atual para pesquisar outro arquivo.")
            continue
        if not processo_ativo:
            try:
                iniciar(nome_arquivo)
                iniciou_aqui = True
            except (RuntimeError, FileNotFoundError, ValueError) as erro:
                erros.append(f"{nome_arquivo}: {erro}")
                continue
        try:
            params = urllib.parse.urlencode({
                "pattern": termo, "books.name": _zim_name(nome_arquivo),
                "format": "xml", "pageLength": limite,
            })
            requisicao = urllib.request.Request(
                f"http://{HOST}:{_porta_ativa}/search?{params}",
                headers={"Accept": "application/xml", "User-Agent": "Optimus/1"},
            )
            with urllib.request.urlopen(requisicao, timeout=12) as resposta:
                resultados.extend(_xml_resultados(resposta.read(4 * 1024 * 1024), nome_arquivo))
        except urllib.error.HTTPError as erro:
            erros.append(f"{nome_arquivo}: Kiwix HTTP {erro.code}; o arquivo pode não conter índice de texto completo.")
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as erro:
            erros.append(f"{nome_arquivo}: falha na busca ({type(erro).__name__}).")
        finally:
            if iniciou_aqui:
                parar()
        if len(resultados) >= limite:
            break
    return {
        "consulta": termo, "resultados": resultados[:limite],
        "total": len(resultados[:limite]), "erros": erros,
        "aviso": "A pesquisa usa o índice textual que já existe dentro de cada ZIM. "
                 "Arquivos sem índice de texto completo não retornam resultados.",
    }


def parar() -> dict:
    """Encerra exclusivamente o processo Popen criado por esta instância."""
    global _processo, _arquivo_ativo
    with _lock:
        processo = _processo
        if processo is not None and processo.poll() is None:
            processo.terminate()
            try:
                processo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=3)
        _processo = None
        _arquivo_ativo = None
        return estado()


atexit.register(parar)
