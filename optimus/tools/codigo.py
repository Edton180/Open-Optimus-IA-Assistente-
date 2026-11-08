"""Modo programador: ferramentas para ler, editar, testar e versionar código.

Funciona como um agente de programação de terminal: o Optimus lê o projeto, procura no
código, faz edições pontuais (procurar e substituir), roda os testes, olha o erro, corrige e
faz commit. Também gerencia containers Docker.

Segurança: ler e consultar é livre; editar, commitar e subir containers é moderado;
push, reset --hard, apagar containers e afins são críticos e sempre pedem confirmação.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from optimus.safety import CRITICO, LIVRE, MODERADO, Avaliacao, caminho_de_sistema
from optimus.tools.base import ferramenta, numero, resolver, texto

_IGNORAR = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
            ".mypy_cache", ".pytest_cache", ".ruff_cache", ".next", "target", ".idea"}


def _rodar(programa: list[str], pasta: Path, limite: int = 300) -> dict:
    try:
        r = subprocess.run(programa, capture_output=True, text=True, cwd=str(pasta),
                           timeout=limite, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {"erro": f"Programa não encontrado: {programa[0]}"}
    except subprocess.TimeoutExpired:
        return {"erro": f"Passou de {limite}s e foi interrompido."}
    return {"codigo": r.returncode, "saida": (r.stdout or "")[-12000:],
            "erros": (r.stderr or "")[-6000:]}


@ferramenta(
    "ler_codigo",
    "Lê um arquivo de código com números de linha (use antes de editar). Dá para ler só um "
    "trecho com inicio/fim.",
    {"caminho": texto("Arquivo"), "inicio": numero("Linha inicial (opcional)"),
     "fim": numero("Linha final (opcional)")},
    grupo="arquivos", obrigatorios=["caminho"],
)
def ler_codigo(ctx, caminho: str, inicio: int = 0, fim: int = 0):
    alvo = resolver(ctx, caminho)
    linhas = alvo.read_text(encoding="utf-8", errors="replace").splitlines()
    inicio = max(1, int(inicio or 1))
    fim = min(len(linhas), int(fim or inicio + 399))
    trecho = "\n".join(f"{n:>5}  {linhas[n - 1]}" for n in range(inicio, fim + 1))
    return {"caminho": str(alvo), "total_linhas": len(linhas), "de": inicio, "ate": fim,
            "codigo": trecho}


def _risco_editar(args, ctx) -> Avaliacao:
    alvo = resolver(ctx, args.get("caminho", ""))
    if caminho_de_sistema(str(alvo)):
        return Avaliacao(CRITICO, f"editar arquivo do sistema {alvo}")
    return Avaliacao(MODERADO, f"editar {alvo}")


@ferramenta(
    "editar_arquivo",
    "Edita um arquivo trocando um trecho exato por outro (como um editor de código). O trecho "
    "'procurar' precisa aparecer uma única vez; inclua linhas vizinhas para ser único. Para "
    "criar arquivo novo use escrever_arquivo.",
    {"caminho": texto("Arquivo"), "procurar": texto("Trecho atual, exatamente como está"),
     "substituir": texto("Trecho novo"),
     "todas": {"type": "boolean", "description": "Trocar todas as ocorrências"}},
    grupo="arquivos", risco=_risco_editar, obrigatorios=["caminho", "procurar", "substituir"],
)
def editar_arquivo(ctx, caminho: str, procurar: str, substituir: str, todas: bool = False):
    alvo = resolver(ctx, caminho)
    conteudo = alvo.read_text(encoding="utf-8")
    vezes = conteudo.count(procurar)
    if vezes == 0:
        return {"erro": "Trecho não encontrado. Leia o arquivo de novo com ler_codigo e copie "
                        "o trecho exatamente."}
    if vezes > 1 and not todas:
        return {"erro": f"O trecho aparece {vezes} vezes. Inclua mais linhas para ser único "
                        "ou use todas=true."}
    novo = conteudo.replace(procurar, substituir) if todas else \
        conteudo.replace(procurar, substituir, 1)
    alvo.write_text(novo, encoding="utf-8")
    return {"mensagem": f"Editado {alvo} ({vezes if todas else 1} troca(s))."}


@ferramenta(
    "buscar_no_codigo",
    "Procura um texto ou expressão regular dentro dos arquivos de um projeto (como grep). "
    "Devolve arquivo, linha e trecho.",
    {"padrao": texto("Texto ou regex"), "pasta": texto("Pasta do projeto (opcional)"),
     "arquivos": texto("Filtro de nomes, ex.: *.py (opcional)")},
    grupo="arquivos", obrigatorios=["padrao"],
)
def buscar_no_codigo(ctx, padrao: str, pasta: str = "", arquivos: str = ""):
    base = resolver(ctx, pasta) if pasta else ctx.pasta_trabalho
    if shutil.which("rg"):
        comando = ["rg", "-n", "--no-heading", "-S", "--max-count", "20", padrao, str(base)]
        if arquivos:
            comando[1:1] = ["-g", arquivos]
        saida = _rodar(comando, base, 60)
        linhas = (saida.get("saida") or "").splitlines()[:200]
        return {"total": len(linhas), "resultados": linhas}
    try:
        regex = re.compile(padrao, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(padrao), re.IGNORECASE)
    resultados: list[str] = []
    for raiz, pastas, nomes in os.walk(base):
        pastas[:] = [p for p in pastas if p not in _IGNORAR]
        for nome in nomes:
            if arquivos and not fnmatch.fnmatch(nome, arquivos):
                continue
            caminho = Path(raiz) / nome
            try:
                if caminho.stat().st_size > 1_000_000:
                    continue
                with open(caminho, encoding="utf-8", errors="strict") as arquivo:
                    for numero_linha, linha in enumerate(arquivo, 1):
                        if regex.search(linha):
                            resultados.append(f"{caminho}:{numero_linha}:{linha.strip()[:200]}")
                            if len(resultados) >= 200:
                                return {"total": len(resultados), "resultados": resultados}
            except (OSError, UnicodeDecodeError):
                continue
    return {"total": len(resultados), "resultados": resultados}


_GIT_LIVRE = {"status", "diff", "log", "show", "branch", "remote", "blame", "ls-files",
              "rev-parse", "describe", "shortlog", "tag"}
_GIT_CRITICO = re.compile(r"^(push|reset\s+--hard|clean|rebase|filter-branch|reflog\s+expire|"
                          r"gc\s+--prune|branch\s+-D|checkout\s+--\s|restore\s|stash\s+(drop|clear))")


def risco_git(argumentos: str) -> int:
    args = argumentos.strip()
    if not args:
        return LIVRE
    if _GIT_CRITICO.search(args) or "--force" in args or re.search(r"\s-f\b", args):
        return CRITICO
    primeiro = args.split()[0]
    if primeiro in _GIT_LIVRE and not re.search(r"^(branch|tag|remote)\s+\S", args):
        return LIVRE
    return MODERADO


@ferramenta(
    "git",
    "Roda um comando git no projeto: status, diff, log, add, commit, branch, checkout, pull, "
    "push... Escreva só o que vem depois de 'git'.",
    {"argumentos": texto("Ex.: status | add -A | commit -m \"Corrige login\" | log --oneline -5"),
     "pasta": texto("Pasta do repositório (opcional)")},
    grupo="comandos", obrigatorios=["argumentos"],
    risco=lambda a, c: Avaliacao(risco_git(a.get("argumentos", "")),
                                 f"git {a.get('argumentos', '')}"),
)
def git(ctx, argumentos: str, pasta: str = ""):
    base = resolver(ctx, pasta) if pasta else ctx.pasta_trabalho
    try:
        partes = shlex.split(argumentos, posix=os.name != "nt")
    except ValueError as erro:
        return {"erro": f"Argumentos inválidos: {erro}"}
    return _rodar(["git", *partes], base, 180)


_DOCKER_LIVRE = {"ps", "images", "logs", "inspect", "stats", "version", "info", "top",
                 "port", "diff", "history", "search"}
_DOCKER_CRITICO = re.compile(r"^(rm|rmi|kill|system\s+prune|volume\s+(rm|prune)|"
                             r"image\s+prune|container\s+prune|network\s+(rm|prune)|"
                             r"compose\s+down\s+.*-v)|--privileged|-v\s+/:/")


def risco_docker(argumentos: str) -> int:
    args = argumentos.strip()
    if not args:
        return LIVRE
    if _DOCKER_CRITICO.search(args):
        return CRITICO
    primeiro = args.split()[0]
    if primeiro in _DOCKER_LIVRE or re.match(r"compose\s+(ps|logs|config)\b", args):
        return LIVRE
    return MODERADO


@ferramenta(
    "docker",
    "Gerencia containers Docker: ps, images, logs, run, build, compose up/down, stop, exec... "
    "Escreva só o que vem depois de 'docker'.",
    {"argumentos": texto("Ex.: ps -a | compose up -d | logs --tail 50 web | build -t app ."),
     "pasta": texto("Pasta (para build e compose)")},
    grupo="comandos", obrigatorios=["argumentos"],
    risco=lambda a, c: Avaliacao(risco_docker(a.get("argumentos", "")),
                                 f"docker {a.get('argumentos', '')}"),
)
def docker(ctx, argumentos: str, pasta: str = ""):
    if not shutil.which("docker"):
        return {"erro": "Docker não está instalado neste PC (https://docs.docker.com/get-docker)."}
    base = resolver(ctx, pasta) if pasta else ctx.pasta_trabalho
    try:
        partes = shlex.split(argumentos, posix=os.name != "nt")
    except ValueError as erro:
        return {"erro": f"Argumentos inválidos: {erro}"}
    return _rodar(["docker", *partes], base, 900)


def detectar_testes(pasta: Path) -> list[str] | None:
    """Descobre como rodar os testes do projeto."""
    if (pasta / "pyproject.toml").exists() or (pasta / "pytest.ini").exists() or \
            (pasta / "tests").is_dir() or (pasta / "setup.py").exists():
        python = shutil.which("python") or shutil.which("python3") or "python"
        return [python, "-m", "pytest", "-q", "-x"]
    if (pasta / "package.json").exists():
        return ["npm", "test", "--silent"]
    if (pasta / "Cargo.toml").exists():
        return ["cargo", "test", "-q"]
    if (pasta / "go.mod").exists():
        return ["go", "test", "./..."]
    if (pasta / "pom.xml").exists():
        return ["mvn", "-q", "test"]
    if (pasta / "build.gradle").exists() or (pasta / "build.gradle.kts").exists():
        return ["gradle", "test", "-q"]
    return None


@ferramenta(
    "rodar_testes",
    "Roda os testes do projeto (detecta pytest, npm, cargo, go, maven, gradle) e devolve o "
    "resultado com os erros, para você corrigir.",
    {"pasta": texto("Pasta do projeto (opcional)"),
     "filtro": texto("Opcional: só alguns testes (nome ou caminho)")},
    grupo="comandos", obrigatorios=[], risco=lambda a, c: Avaliacao(MODERADO, "rodar os testes"),
)
def rodar_testes(ctx, pasta: str = "", filtro: str = ""):
    base = resolver(ctx, pasta) if pasta else ctx.pasta_trabalho
    comando = detectar_testes(base)
    if not comando:
        return {"erro": "Não achei testes neste projeto. Diga qual comando usar."}
    if filtro:
        comando.append(filtro)
    resultado = _rodar(comando, base, 900)
    resultado["comando"] = " ".join(comando)
    if "codigo" in resultado:
        resultado["passou"] = resultado["codigo"] == 0
    return resultado
