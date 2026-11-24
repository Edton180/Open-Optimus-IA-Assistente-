"""Inventário leve e somente de leitura dos módulos locais do Optimus.

Não instala, inicia, para nem altera serviços. Estados são derivados de executáveis
presentes e health-checks locais com timeout curto.
"""
from __future__ import annotations

import shutil
import subprocess
import psutil
from urllib.request import urlopen
from urllib.error import URLError


def _processo(*termos: str) -> bool:
    procurados = tuple(t.casefold() for t in termos)
    try:
        for proc in psutil.process_iter(("name", "cmdline")):
            try:
                nome = (proc.info.get("name") or "").casefold()
                cmd = " ".join(proc.info.get("cmdline") or []).casefold()
                if any(t in nome or t in cmd for t in procurados):
                    return True
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
    except (psutil.Error, OSError):
        return False
    return False


def _http(url: str) -> bool:
    try:
        with urlopen(url, timeout=0.6) as resposta:
            return 200 <= resposta.status < 300
    except (OSError, URLError, TimeoutError):
        return False


def _servico(nome: str, descricao: str, executaveis: tuple[str, ...],
             host: str, port: int, url: str = "", processos: tuple[str, ...] = ()) -> dict:
    executavel = next((shutil.which(item) for item in executaveis if shutil.which(item)), None)
    ativo = (_http(url) and (not processos or _processo(*processos))) if url else _processo(*processos) if processos else False
    if ativo:
        estado, detalhe = ("disponivel", f"Respondendo em {host}:{port}") if url else ("disponivel", "Processo ativo no sistema")
    elif executavel:
        estado, detalhe = "instalado_parado", f"Executável encontrado: {executavel}; serviço não respondeu"
    else:
        estado, detalhe = "nao_instalado", "Nenhum executável conhecido foi encontrado"
    return {"id": nome, "nome": nome, "descricao": descricao, "estado": estado,
            "detalhe": detalhe, "executavel": bool(executavel)}


def _kiwix() -> dict:
    """Usa a mesma fonte de verdade do Leitor Kiwix, inclusive a instalação privada."""
    from optimus import kiwix

    dados = kiwix.estado()
    if dados.get("executando"):
        estado, detalhe = "disponivel", "Servidor Kiwix iniciado pelo Optimus e respondendo nesta sessão"
    elif dados.get("instalado") and dados.get("gerenciado"):
        estado, detalhe = "instalado_parado", (
            f"Kiwix Tools {dados.get('versao') or ''} instalado na pasta privada do Optimus; "
            "leitor parado até solicitação"
        )
    elif dados.get("instalado"):
        estado, detalhe = "instalado_parado", "Kiwix encontrado no sistema; leitor parado"
    else:
        estado, detalhe = "nao_instalado", dados.get("erro") or "Nenhum executável Kiwix conhecido foi encontrado"
    return {"id": "Kiwix", "nome": "Kiwix",
            "descricao": "Servidor e leitor de bibliotecas offline no formato ZIM.",
            "estado": estado, "detalhe": detalhe,
            "executavel": bool(dados.get("executavel_disponivel")),
            "gerenciado": bool(dados.get("gerenciado")),
            "executando": bool(dados.get("executando")),
            "versao": dados.get("versao")}


def _docker() -> dict:
    """Confirma o daemon via Docker CLI; encontrar um processo não prova disponibilidade."""
    executavel = shutil.which("docker")
    if not executavel:
        return {"id": "Docker", "nome": "Docker",
                "descricao": "Runtime opcional para aplicativos e serviços isolados.",
                "estado": "nao_instalado", "detalhe": "Docker CLI não foi encontrado",
                "executavel": False}
    try:
        resultado = subprocess.run(
            [executavel, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        versao = (resultado.stdout or "").strip()
        if resultado.returncode == 0 and versao:
            estado, detalhe = "disponivel", f"Daemon Docker respondendo · Engine {versao}"
        else:
            erro = (resultado.stderr or resultado.stdout or "").strip().splitlines()
            detalhe_erro = erro[0][:240] if erro else "daemon não respondeu"
            estado, detalhe = "instalado_parado", f"Docker CLI instalado, mas daemon indisponível: {detalhe_erro}"
    except subprocess.TimeoutExpired:
        estado, detalhe = "instalado_parado", "Docker CLI instalado, mas o daemon excedeu o tempo de diagnóstico"
    except OSError as erro:
        estado, detalhe = "instalado_parado", f"Docker CLI encontrado, mas não pôde ser executado: {erro}"
    return {"id": "Docker", "nome": "Docker",
            "descricao": "Runtime opcional para aplicativos e serviços isolados.",
            "estado": estado, "detalhe": detalhe, "executavel": True}


def inventario() -> list[dict]:
    """Retorna o estado observado sem executar comandos privilegiados ou iniciar serviços."""
    return [
        {"id": "Optimus Core", "nome": "Optimus Core",
         "descricao": "Agente local, interface, memória SQLite, ferramentas e perfis de hardware.",
         "estado": "nativo", "detalhe": "Parte integrante desta instalação", "executavel": True},
        _servico("Ollama", "Motor de modelos de IA locais.",
                 ("ollama",), "127.0.0.1", 11434, "http://127.0.0.1:11434/api/tags"),
        _kiwix(),
        _servico("Kolibri", "Plataforma de aprendizagem e conteúdo educacional offline.",
                 ("kolibri",), "127.0.0.1", 8080, "http://127.0.0.1:8080/",
                 processos=("kolibri",)),
        _servico("Qdrant", "Banco vetorial opcional para busca semântica avançada.",
                 ("qdrant",), "127.0.0.1", 6333, "http://127.0.0.1:6333/healthz"),
        _docker(),
    ]



def recursos() -> dict:
    """Métricas locais resumidas; não coleta nomes de usuário nem caminhos pessoais."""
    memoria = psutil.virtual_memory()
    try:
        disco = psutil.disk_usage(str(__import__("pathlib").Path.home().anchor or "/"))
    except (OSError, ValueError):
        disco = None
    try:
        cpu = psutil.cpu_percent(interval=None)
        frequencia = psutil.cpu_freq()
    except (psutil.Error, OSError):
        cpu, frequencia = 0.0, None
    return {
        "cpu_percentual": round(float(cpu), 1),
        "cpu_nucleos_logicos": psutil.cpu_count(logical=True) or 0,
        "cpu_nucleos_fisicos": psutil.cpu_count(logical=False) or 0,
        "memoria_total_bytes": int(memoria.total),
        "memoria_disponivel_bytes": int(memoria.available),
        "memoria_percentual": round(float(memoria.percent), 1),
        "disco_total_bytes": int(disco.total) if disco else None,
        "disco_livre_bytes": int(disco.free) if disco else None,
        "disco_percentual": round(float(disco.percent), 1) if disco else None,
        "processos": len(psutil.pids()),
        "uptime_segundos": max(0, int(__import__("time").time() - psutil.boot_time())),
        "cpu_frequencia_mhz": round(float(frequencia.current), 0) if frequencia else None,
    }
