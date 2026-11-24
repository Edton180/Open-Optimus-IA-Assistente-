"""Provisionamento local e gerenciamento do Home Assistant Container.

O Optimus gerencia o ciclo de vida do container sem exigir que o usuário opere Docker
manualmente. O runtime Docker continua sendo um pré-requisito do sistema e sua instalação
pode solicitar autorização administrativa do próprio sistema operacional.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
import threading
import time
from pathlib import Path
from typing import Any

from optimus.config import pasta_base

NOME = "optimus-home-assistant"
IMAGEM = "ghcr.io/home-assistant/home-assistant:stable"
PORTA = 8123
_LOCK = threading.Lock()
_TAREFA: dict[str, Any] = {"estado": "ocioso", "mensagem": "", "erro": "", "atualizado": 0.0}


def _pasta() -> Path:
    p = pasta_base() / "home_assistant"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _comando_docker() -> list[str] | None:
    exe = shutil.which("docker")
    if exe:
        return [exe]
    if platform.system() == "Windows":
        candidatos = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Docker/Docker/resources/bin/docker.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Docker/Docker/resources/bin/docker",
        ]
        for p in candidatos:
            if p.is_file():
                return [str(p)]
    return None


def _executar(args: list[str], timeout: int = 45, check: bool = True, elevate: bool = False) -> subprocess.CompletedProcess:
    base = _comando_docker()
    if not base:
        raise RuntimeError("Docker não está instalado. Use 'Instalar ambiente' nesta tela.")
    cmd = base + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("O comando Docker excedeu o tempo limite. Verifique se o Docker está iniciado.") from exc
    detalhe = (p.stderr or p.stdout or "").strip()
    if elevate and p.returncode and ("permission denied" in detalhe.lower() or "access is denied" in detalhe.lower()):
        pkexec = shutil.which("pkexec") if platform.system() == "Linux" else None
        if pkexec:
            try:
                p = subprocess.run([pkexec, *cmd], capture_output=True, text=True,
                                   timeout=timeout, check=False)
                detalhe = (p.stderr or p.stdout or "").strip()
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("A operação Docker autorizada excedeu o tempo limite.") from exc
    if p.returncode and check:
        detalhe = (p.stderr or p.stdout or "erro sem detalhes").strip()[-1200:]
        if "permission denied" in detalhe.lower() or "access is denied" in detalhe.lower():
            raise RuntimeError("Docker está instalado, mas não foi possível obter autorização para acessá-lo. Verifique as permissões do serviço Docker.")
        if "Cannot connect to the Docker daemon" in detalhe or "Is the docker daemon running" in detalhe:
            raise RuntimeError("O serviço Docker está parado. Inicie o Docker e tente novamente.")
        raise RuntimeError(f"Docker não concluiu a operação: {detalhe}")
    return p


def _runtime() -> dict[str, Any]:
    sistema = platform.system()
    docker = _comando_docker()
    resultado = {
        "sistema": sistema, "suportado": sistema in ("Linux", "Windows"),
        "docker_instalado": bool(docker), "docker_ativo": False,
        "docker_versao": "", "metodo": "Docker Engine / Docker Desktop",
        "observacao": "",
    }
    if sistema == "Darwin":
        resultado["suportado"] = True
        resultado["observacao"] = "No macOS, instale/abra Docker Desktop; o provisionamento do container é gerenciado pelo Optimus."
    elif sistema not in ("Linux", "Windows"):
        resultado["observacao"] = "Este sistema operacional ainda não possui provisionamento validado."
    if docker:
        try:
            p = _executar(["version", "--format", "{{.Server.Version}}"], timeout=8, check=False)
            resultado["docker_ativo"] = p.returncode == 0 and bool(p.stdout.strip())
            resultado["docker_versao"] = p.stdout.strip()[:80]
            detalhe = (p.stderr or "").lower()
            if p.returncode and ("permission denied" in detalhe or "access is denied" in detalhe):
                resultado["docker_ativo"] = None
                resultado["observacao"] = "Docker instalado, mas exige autorização administrativa para consultar/gerenciar o serviço."
        except Exception as exc:
            resultado["observacao"] = str(exc)
    return resultado


def _container(elevate: bool = False) -> dict[str, Any]:
    p = _executar(["inspect", "--format", "{{.State.Status}}|{{.State.Running}}|{{.Config.Image}}", NOME], timeout=12, check=False, elevate=elevate)
    if p.returncode:
        return {"instalado": False, "estado": "nao_instalado", "rodando": False}
    partes = p.stdout.strip().split("|", 2)
    estado = partes[0] if partes else "desconhecido"
    rodando = len(partes) > 1 and partes[1].lower() == "true"
    return {"instalado": True, "estado": estado, "rodando": rodando,
            "imagem": partes[2] if len(partes) > 2 else IMAGEM}


def _healthcheck(timeout: float = 2.0) -> dict[str, Any]:
    """Confirma que a interface HTTP do Home Assistant responde localmente."""
    try:
        import httpx
        resposta = httpx.get(f"http://127.0.0.1:{PORTA}/", timeout=timeout,
                             follow_redirects=False)
        return {"saudavel": resposta.status_code < 500,
                "http_status": resposta.status_code}
    except Exception as exc:
        return {"saudavel": False, "http_status": None,
                "observacao": type(exc).__name__}


def estado() -> dict[str, Any]:
    runtime = _runtime()
    try:
        container = _container() if runtime["docker_ativo"] is True else {
            "instalado": False,
            "estado": "permissao_pendente" if runtime["docker_ativo"] is None else "runtime_indisponivel",
            "rodando": False}
        erro = ""
    except Exception as exc:
        container = {"instalado": False, "estado": "erro", "rodando": False}
        erro = str(exc)
    if container.get("estado") == "permissao_pendente":
        try:
            import httpx
            resposta = httpx.get(f"http://127.0.0.1:{PORTA}/", timeout=1.5,
                                 follow_redirects=False)
            container = {"instalado": True, "estado": "running",
                         "rodando": resposta.status_code < 500,
                         "verificacao": "HTTP local"}
        except Exception:
            pass
    if container.get("rodando"):
        container.update(_healthcheck())
    try:
        tarefa = dict(_TAREFA)
    except Exception:
        tarefa = {}
    return {
        "runtime": runtime, "container": container, "tarefa": tarefa,
        "url": f"http://127.0.0.1:{PORTA}" if container.get("rodando") else "",
        "erro": erro,
        "dados": str(_pasta()),
        "nota": "Home Assistant Container (sem Supervisor/add-ons do Home Assistant OS). Integrações e dispositivos são gerenciados pela interface do Home Assistant.",
    }


def _definir_tarefa(status: str, mensagem: str = "", erro: str = "") -> None:
    _TAREFA.update(estado=status, mensagem=mensagem, erro=erro, atualizado=time.time())


def _instalar_runtime_linux() -> None:
    """Instala Docker Engine em Debian/Ubuntu por autorização gráfica pkexec."""
    if platform.system() != "Linux":
        raise RuntimeError("Instalação automática do runtime ainda depende do instalador oficial do Docker Desktop neste sistema.")
    if not shutil.which("pkexec"):
        raise RuntimeError("Não encontrei pkexec para solicitar autorização administrativa. Instale Docker Engine pelo gerenciador de pacotes ou disponibilize pkexec e tente novamente.")
    if not shutil.which("apt-get"):
        raise RuntimeError("A instalação automática do runtime está validada apenas em Debian/Ubuntu (apt). Neste Linux, instale Docker Engine pelo gerenciador de pacotes.")
    pkexec = shutil.which("pkexec")
    comandos = [
        [pkexec, "apt-get", "update"],
        [pkexec, "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "docker.io"],
        [pkexec, "systemctl", "enable", "--now", "docker"],
    ]
    for comando in comandos:
        p = subprocess.run(comando, capture_output=True, text=True, timeout=900, check=False)
        if p.returncode:
            detalhe = (p.stderr or p.stdout or "autorização cancelada").strip()[-1000:]
            raise RuntimeError(f"Não foi possível instalar/iniciar Docker: {detalhe}")
    if not _comando_docker():
        raise RuntimeError("A instalação terminou, mas o executável Docker não foi localizado.")


def instalar_ambiente() -> dict[str, Any]:
    """Instala o runtime apenas após autorização do SO; no Windows inicia winget."""
    runtime = _runtime()
    if runtime["docker_instalado"]:
        if runtime["docker_ativo"] is not True:
            try:
                _executar(["version", "--format", "{{.Server.Version}}"], timeout=15, elevate=True)
            except Exception as exc:
                raise RuntimeError("Docker já está instalado, mas precisa ser iniciado ou autorizado. Abra o Docker Desktop ou autorize o serviço Docker e tente novamente.") from exc
        return {"ok": True, "mensagem": "Docker já está instalado e ativo."}
    if platform.system() == "Linux":
        _instalar_runtime_linux()
    elif platform.system() == "Darwin":
        brew = shutil.which("brew")
        if not brew:
            raise RuntimeError("Homebrew não foi encontrado. O Optimus pode instalar o Docker Desktop automaticamente quando o Homebrew estiver disponível.")
        p = subprocess.run([brew, "install", "--cask", "docker"],
                           capture_output=True, text=True, timeout=1800, check=False)
        if p.returncode:
            raise RuntimeError("A instalação do Docker Desktop pelo Homebrew falhou: " +
                               (p.stderr or p.stdout or "erro sem detalhes")[-1000:])
        subprocess.Popen(["open", "-a", "Docker"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        limite = time.monotonic() + 240
        while time.monotonic() < limite:
            if _runtime().get("docker_ativo") is True:
                return {"ok": True, "mensagem": "Docker Desktop instalado e inicializado."}
            time.sleep(4)
        raise RuntimeError("Docker Desktop foi instalado, mas ainda não respondeu. Verifique a virtualização e conclua a primeira abertura do Docker Desktop.")
    elif platform.system() == "Windows":
        winget = shutil.which("winget")
        if not winget:
            raise RuntimeError("O Windows Package Manager (winget) não está disponível. Instale/atualize o App Installer da Microsoft e tente novamente.")
        p = subprocess.run([winget, "install", "--exact", "--id", "Docker.DockerDesktop",
                            "--accept-package-agreements", "--accept-source-agreements"],
                           capture_output=True, text=True, timeout=1200, check=False)
        if p.returncode not in (0, 3010):
            raise RuntimeError(f"Instalação do Docker Desktop falhou: {(p.stderr or p.stdout)[-1000:]}")
        exe = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Docker/Docker/Docker Desktop.exe"
        if exe.is_file():
            subprocess.Popen([str(exe)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             close_fds=True)
        if p.returncode == 3010:
            return {"ok": True, "reiniciar": True,
                    "mensagem": "Docker Desktop instalado. O Windows solicitou reinicialização para concluir a instalação; reinicie e o Optimus continuará automaticamente na próxima abertura."}
        limite = time.monotonic() + 240
        ultimo = ""
        while time.monotonic() < limite:
            estado_runtime = _runtime()
            if estado_runtime.get("docker_ativo") is True:
                return {"ok": True, "mensagem": "Docker Desktop instalado e inicializado."}
            ultimo = estado_runtime.get("observacao", "")
            time.sleep(4)
        detalhe = (" " + ultimo) if ultimo else ""
        raise RuntimeError("Docker Desktop foi instalado e aberto, mas o motor ainda não ficou pronto. "
                           "O Optimus aguardou 4 minutos. Verifique WSL 2/virtualização e conclua "
                           "a configuração inicial do Docker Desktop; depois use Atualizar status."
                           + detalhe)
    else:
        raise RuntimeError("Instalação automática do Docker não disponível neste sistema.")
    return {"ok": True, "mensagem": "Docker Engine instalado e iniciado."}


def instalar() -> dict[str, Any]:
    runtime = _runtime()
    if not runtime["suportado"]:
        raise RuntimeError("Este sistema operacional não está na matriz de provisionamento suportada.")
    if not runtime["docker_instalado"]:
        resultado_runtime = instalar_ambiente()
        if resultado_runtime.get("reiniciar"):
            return resultado_runtime
        runtime = _runtime()
    if runtime["docker_ativo"] is not True:
        try:
            _executar(["version", "--format", "{{.Server.Version}}"], timeout=15, elevate=True)
        except Exception as exc:
            raise RuntimeError("Docker está instalado, mas não está ativo ou requer autorização. Abra o Docker Desktop (Windows/macOS) ou autorize o serviço Docker (Linux) e tente novamente.") from exc
    dados = _pasta()
    _executar(["pull", IMAGEM], timeout=900, elevate=True)
    existente = _container(elevate=True)
    if existente["instalado"]:
        if existente["rodando"]:
            return {"ok": True, "mensagem": "Home Assistant já está em execução.", "url": f"http://127.0.0.1:{PORTA}"}
        _executar(["rm", "-f", NOME], timeout=30, elevate=True)
    args = ["run", "-d", "--name", NOME, "--restart", "unless-stopped",
            "-e", f"TZ={os.environ.get('TZ', 'America/Sao_Paulo')}",
            "-v", f"{dados.resolve()}:/config"]
    if platform.system() == "Linux":
        args += ["--network", "host"]
    else:
        args += ["-p", f"{PORTA}:8123"]
    args += [IMAGEM]
    _executar(args, timeout=90, elevate=True)
    for _ in range(120):
        time.sleep(2)
        st = _container(elevate=True)
        if st["rodando"] and _healthcheck(timeout=2).get("saudavel"):
            return {"ok": True, "mensagem": "Home Assistant instalado, iniciado e respondendo ao health-check HTTP.", "url": f"http://127.0.0.1:{PORTA}"}
    raise RuntimeError("O container foi criado, mas o Home Assistant não passou no health-check após 4 minutos. Os dados foram preservados; consulte os logs antes de tentar novamente.")


def acao(nome: str) -> dict[str, Any]:
    if nome == "instalar":
        return instalar()
    if nome == "iniciar":
        _executar(["start", NOME], elevate=True)
    elif nome == "parar":
        _executar(["stop", NOME], timeout=60, elevate=True)
    elif nome == "reiniciar":
        _executar(["restart", NOME], timeout=90, elevate=True)
    elif nome == "atualizar":
        dados = _pasta()
        _executar(["pull", IMAGEM], timeout=900, elevate=True)
        _executar(["stop", NOME], timeout=60, check=False, elevate=True)
        _executar(["rm", "-f", NOME], timeout=30, elevate=True)
        args = ["run", "-d", "--name", NOME, "--restart", "unless-stopped",
                "-e", f"TZ={os.environ.get('TZ', 'America/Sao_Paulo')}",
                "-v", f"{dados.resolve()}:/config"]
        args += ["--network", "host"] if platform.system() == "Linux" else ["-p", f"{PORTA}:8123"]
        args += [IMAGEM]
        _executar(args, timeout=90, elevate=True)
    elif nome == "backup":
        destino = pasta_base() / "backups"
        destino.mkdir(parents=True, exist_ok=True)
        arquivo = destino / f"home-assistant-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
        with tarfile.open(arquivo, "w:gz") as tar:
            tar.add(_pasta(), arcname="home_assistant")
        return {"ok": True, "mensagem": "Backup criado; a configuração original foi preservada.",
                "arquivo": str(arquivo)}
    elif nome == "desinstalar":
        _executar(["stop", NOME], timeout=60, check=False, elevate=True)
        _executar(["rm", "-f", NOME], timeout=30, check=False, elevate=True)
        return {"ok": True, "mensagem": "Container removido. Os dados e backups foram preservados.",
                "dados": str(_pasta())}
    elif nome == "logs":
        p = _executar(["logs", "--tail", "100", NOME], timeout=20, check=False, elevate=True)
        return {"ok": True, "logs": (p.stdout + p.stderr)[-16000:]}
    else:
        raise ValueError("Ação desconhecida.")
    return {"ok": True, "mensagem": f"Ação '{nome}' concluída."}


def executar_acao(nome: str) -> dict[str, Any]:
    """Serializa alterações de lifecycle para evitar operações concorrentes."""
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("Já existe uma operação do Home Assistant em andamento.")
    try:
        _definir_tarefa("executando", f"Executando: {nome}")
        resultado = acao(nome)
        _definir_tarefa("concluido", resultado.get("mensagem", "Operação concluída."))
        _TAREFA["resultado"] = resultado
        return resultado
    except Exception as exc:
        _definir_tarefa("falhou", "", str(exc))
        raise
    finally:
        _LOCK.release()
