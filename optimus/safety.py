"""Segurança das ações no PC.

O Optimus não filtra conversa: quem decide o modelo e a personalidade é o usuário.
O que ele protege são as AÇÕES no computador, para um erro do modelo não apagar seus
arquivos. Cada chamada de ferramenta recebe um nível de risco:

    0 livre      leitura e consultas (ver arquivos, pesquisar, hora, sistema)
    1 moderado   cria ou muda coisas que dá para desfazer (escrever arquivo novo,
                 abrir programa, digitar, comando desconhecido)
    2 crítico    difícil de desfazer (apagar, sobrescrever, matar processo,
                 desligar, reiniciar, instalar, comandos destrutivos)
    3 bloqueado  destrói o sistema (formatar disco, apagar a raiz, fork bomb,
                 PowerShell codificado). Nunca roda pelo Optimus.

O modo do agente decide o que pede confirmação:
    seguro       pergunta a partir do nível 1
    equilibrado  pergunta a partir do nível 2 (padrão)
    autonomo     também pergunta a partir do nível 2: ações críticas sempre perguntam.
                 A diferença é que no modo autônomo o agente planeja e encadeia
                 mais passos sozinho.

A ideia dos níveis com confirmação estrita (negação sempre vence) vem de assistentes
de voz da comunidade, como o huburton/jarvis.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

LIVRE, MODERADO, CRITICO, BLOQUEADO = 0, 1, 2, 3
NOMES_NIVEL = {0: "livre", 1: "moderado", 2: "crítico", 3: "bloqueado"}

_BLOQUEADOS = [
    r"\brm\s+(-[a-z]*\s+)*-[a-z]*r[a-z]*f?[a-z]*\s+(--no-preserve-root\s+)?(/|/\*|~|~/|\$HOME)\s*$",
    r"\brm\s+(-[a-z]*\s+)*-[a-z]*r[a-z]*\s+--no-preserve-root",
    r"\bmkfs(\.\w+)?\b",
    r"\bdd\b.*\bof=/dev/(sd|nvme|hd|mmcblk|vd)",
    r">\s*/dev/(sd|nvme|hd|mmcblk)[a-z0-9]*\b",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"\bformat(\.com)?\s+[a-z]:",
    r"\bdiskpart\b",
    r"\b(rd|rmdir)\s+/s\s+(/q\s+)?[a-z]:\\?\s*$",
    r"\bdel\s+(/[a-z]\s+)*[a-z]:\\(windows|\*)",
    r"remove-item\s+.*[a-z]:\\windows",
    r"-(e|en|enc|enco|encod|encode|encodedcommand)\s+[a-z0-9+/=]{20,}",
    r"\bcipher\s+/w",
    r"\bbcdedit\b.*/delete",
    r"\bchmod\s+(-r\s+)?0?00\s+/\s*$",
    r"\bchown\s+-r\s+\S+\s+/\s*$",
]

_CRITICOS = [
    r"\brm\b", r"\bdel\b", r"\berase\b", r"\brmdir\b", r"\brd\b", r"remove-item", r"\bshred\b",
    r"\bshutdown\b", r"\breboot\b", r"\bpoweroff\b", r"\bhalt\b", r"restart-computer",
    r"stop-computer", r"\bsystemctl\s+(stop|disable|mask|poweroff|reboot)",
    r"\bkill(all)?\b", r"\bpkill\b", r"\btaskkill\b", r"stop-process",
    r"\bsudo\b", r"\bsu\b\s", r"\brunas\b", r"start-process.*-verb\s+runas",
    r"\b(apt|apt-get|dnf|yum|pacman|zypper|snap|flatpak|winget|choco|scoop)\s+"
    r"(install|remove|purge|uninstall|-s|-r)",
    r"\bpip\s+(install|uninstall)", r"\bnpm\s+(install|uninstall)\s+-g",
    r"\breg\s+(add|delete|import)", r"set-itemproperty", r"new-itemproperty",
    r"\bchmod\b", r"\bchown\b", r"\bmv\b", r"\bmove\b", r"move-item", r"\bren(ame)?\b",
    r">\s*[^&|]", r"\btruncate\b", r"\bgit\s+(push|reset\s+--hard|clean\s+-[a-z]*f)",
    r"\bcrontab\s+-r", r"\bschtasks\s+/(create|delete)", r"\buseradd\b", r"\bnet\s+user\b",
    r"\bcurl\b.*\|\s*(ba)?sh", r"\bwget\b.*\|\s*(ba)?sh", r"\biex\b", r"invoke-expression",
    r"\bformat\b",
]

_SOMENTE_LEITURA = {
    "ls", "dir", "pwd", "cd", "echo", "cat", "type", "head", "tail", "whoami", "hostname",
    "date", "uptime", "df", "du", "free", "uname", "ipconfig", "ifconfig", "ip", "ping",
    "nslookup", "which", "where", "find", "grep", "findstr", "wc", "tree", "ps", "top",
    "tasklist", "systeminfo", "nvidia-smi", "lscpu", "lsblk", "lsusb", "lspci", "env",
    "set", "get-childitem", "get-content", "get-process", "get-date", "get-location",
    "python", "python3", "node", "git", "ver", "sort", "stat", "file", "history",
}


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def risco_comando(comando: str) -> int:
    texto = comando.strip().lower()
    if not texto:
        return LIVRE
    for padrao in _BLOQUEADOS:
        if re.search(padrao, texto):
            return BLOQUEADO
    for padrao in _CRITICOS:
        if re.search(padrao, texto):
            return CRITICO
    partes = re.split(r"\s*(?:&&|\|\||;|\|)\s*", texto)
    if all(p.split()[0] in _SOMENTE_LEITURA for p in partes if p.split()):
        if re.search(r"\bgit\s+(commit|checkout|merge|rebase|stash|branch\s+-d)", texto):
            return MODERADO
        if re.search(r"\b(python3?|node)\s+(-c|-e)\b", texto):
            return MODERADO
        return LIVRE
    return MODERADO


_PASTAS_SISTEMA = [
    "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc", "/sbin", "/sys", "/usr",
    "/var/lib", "c:/windows", "c:/program files", "c:/program files (x86)",
    "c:/programdata", "/system", "/data/system",
]


def caminho_de_sistema(caminho: str) -> bool:
    texto = str(caminho).replace("\\", "/").lower().rstrip("/")
    if texto in ("", "/", "c:", "~"):
        return True
    return any(texto == p or texto.startswith(p + "/") for p in _PASTAS_SISTEMA)


@dataclass
class Avaliacao:
    nivel: int
    motivo: str

    @property
    def bloqueado(self) -> bool:
        return self.nivel >= BLOQUEADO


def precisa_confirmar(nivel: int, modo: str) -> bool:
    if nivel >= BLOQUEADO:
        return False  # nem pergunta: é recusado
    if modo == "seguro":
        return nivel >= MODERADO
    return nivel >= CRITICO


_SIM = {"sim", "pode", "pode sim", "confirmo", "confirma", "autorizo", "ok", "manda",
        "manda ver", "faz", "faca", "faça", "claro", "isso", "positivo", "s", "yes", "y",
        "aprovar", "aprovado", "executa", "executar", "vai"}
_NAO = re.compile(r"\b(nao|no|cancela|cancelar|pare|para|espera|negativo|nunca|jamais|"
                  r"depois|agora nao|nem|recuso|negar|negado)\b")


def interpretar_confirmacao(resposta: str, nivel: int = MODERADO) -> bool:
    """Lê "sim"/"não" com rigor: qualquer negação vence e só um sim claro aprova.

    Ações críticas faladas pedem a palavra "confirmo" (ou "sim, confirmo").
    """
    texto = _normal(resposta).strip(" .!?,")
    if not texto or _NAO.search(texto):
        return False
    if nivel >= CRITICO:
        return bool(re.search(r"\b(confirmo|confirmado|aprovado|aprovar|yes)\b", texto)) or \
            texto in ("sim confirmo", "s")
    palavras = set(re.findall(r"\w+", texto))
    return texto in _SIM or bool(palavras & {"sim", "pode", "confirmo", "autorizo", "claro",
                                             "ok", "yes", "aprovar", "aprovado"})


_SEGREDO = re.compile(
    r"(sk-[a-z0-9_\-]{10,}|ghp_[a-z0-9]{20,}|xox[abp]-[a-z0-9\-]{10,}|"
    r"(?:senha|password|token|api[_-]?key|chave)\s*[=:]\s*\S+)",
    re.IGNORECASE,
)


def mascarar(texto: str) -> str:
    return _SEGREDO.sub("[oculto]", texto)


class Auditoria:
    """Registro das ações executadas (JSON por linha), com senhas e chaves mascaradas."""

    def __init__(self, caminho: Path):
        self.caminho = caminho
        self.caminho.parent.mkdir(parents=True, exist_ok=True)

    def registrar(self, ferramenta: str, argumentos: dict, nivel: int, decisao: str,
                  resultado: str = "") -> None:
        linha = {
            "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ferramenta": ferramenta,
            "argumentos": {
                k: ("[oculto]" if re.search(r"senha|password|token|chave|key", k, re.I)
                    else mascarar(v) if isinstance(v, str) else v)
                for k, v in (argumentos or {}).items()
            },
            "nivel": NOMES_NIVEL.get(nivel, str(nivel)),
            "decisao": decisao,
            "resultado": mascarar(resultado[:500]),
        }
        try:
            with open(self.caminho, "a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
        except (OSError, ValueError):
            pass

    def ultimas(self, quantidade: int = 50) -> list[dict]:
        if not self.caminho.exists():
            return []
        linhas = self.caminho.read_text(encoding="utf-8").splitlines()[-quantidade:]
        saida = []
        for linha in linhas:
            try:
                saida.append(json.loads(linha))
            except json.JSONDecodeError:
                continue
        return list(reversed(saida))
