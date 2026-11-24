"""Inventário leve e somente de leitura dos módulos locais do Optimus.

Não instala, inicia, para nem altera serviços. Estados são derivados de executáveis
presentes e health-checks locais com timeout curto.
"""
from __future__ import annotations

import shutil
import socket
from urllib.request import urlopen
from urllib.error import URLError


def _porta(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False


def _http(url: str) -> bool:
    try:
        with urlopen(url, timeout=0.6) as resposta:
            return 200 <= resposta.status < 500
    except (OSError, URLError, TimeoutError):
        return False


def _servico(nome: str, descricao: str, executaveis: tuple[str, ...],
             host: str, port: int, url: str = "") -> dict:
    executavel = next((shutil.which(item) for item in executaveis if shutil.which(item)), None)
    ativo = _http(url) if url else _porta(host, port)
    if ativo:
        estado, detalhe = "disponivel", f"Respondendo em {host}:{port}"
    elif executavel:
        estado, detalhe = "instalado_parado", f"Executável encontrado: {executavel}; serviço não respondeu"
    else:
        estado, detalhe = "nao_instalado", "Nenhum executável conhecido foi encontrado"
    return {"id": nome, "nome": nome, "descricao": descricao, "estado": estado,
            "detalhe": detalhe, "executavel": bool(executavel)}


def inventario() -> list[dict]:
    """Retorna o estado observado sem executar comandos privilegiados."""
    return [
        {"id": "Optimus Core", "nome": "Optimus Core",
         "descricao": "Agente local, interface, memória SQLite, ferramentas e perfis de hardware.",
         "estado": "nativo", "detalhe": "Parte integrante desta instalação", "executavel": True},
        _servico("Ollama", "Motor de modelos de IA locais.",
                 ("ollama",), "127.0.0.1", 11434, "http://127.0.0.1:11434/api/tags"),
        _servico("Kiwix", "Servidor e leitor de bibliotecas offline no formato ZIM.",
                 ("kiwix-serve", "kiwix-desktop"), "127.0.0.1", 8080),
        _servico("Kolibri", "Plataforma de aprendizagem e conteúdo educacional offline.",
                 ("kolibri",), "127.0.0.1", 8080),
        _servico("Qdrant", "Banco vetorial opcional para busca semântica avançada.",
                 ("qdrant",), "127.0.0.1", 6333, "http://127.0.0.1:6333/healthz"),
        _servico("Docker", "Runtime opcional para aplicativos e serviços isolados.",
                 ("docker",), "127.0.0.1", 2375),
    ]
