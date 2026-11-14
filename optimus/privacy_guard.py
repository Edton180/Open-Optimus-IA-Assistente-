"""Barreira de privacidade (Zero-Leak) para a autoatualização no GitHub.

Antes de qualquer `git add`/`git commit` automático feito pelo próprio Optimus, este
módulo varre o que seria enviado e impede o vazamento de dados pessoais do dono do PC:

- **Bloqueia arquivos inteiros** que nunca devem subir: bancos locais (`.db`, `.sqlite`),
  segredos (`.env`, `*.pem`, `*.key`), o `config.toml` com chaves reais, memórias de longo
  prazo, históricos de conversa, fotos/vídeos das câmeras e backups.
- **Mascara segredos** encontrados dentro de arquivos de código (`.py`, `.md`, `.toml`,
  etc.): chaves de API (OpenAI, Anthropic, GitHub, Google, Groq, Slack, AWS...), tokens,
  senhas, chaves privadas, IPs locais/públicos do usuário, endereços MAC da casa, senhas de
  Wi-Fi e caminhos de pasta com o nome do usuário (`C:\\Users\\...`, `/home/...`).

O masking substitui por marcadores genéricos (`<SUA_API_KEY>`, `<SEU_IP>`, ...). A regra é
estrita: na dúvida, bloqueia. Nada deste módulo faz rede — ele só analisa texto e caminhos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

# --------------------------------------------------------------------------- arquivos proibidos
# Padrões de nome (glob simples) que nunca podem ser versionados automaticamente.
ARQUIVOS_PROIBIDOS: tuple[str, ...] = (
    "*.db", "*.sqlite", "*.sqlite3", "*.db-wal", "*.db-shm",
    ".env", "*.env", "env.local", "*.secret", "*.secrets",
    "*.pem", "*.key", "*.pfx", "*.p12", "*.keystore", "id_rsa", "id_ed25519",
    "config.toml", "config.local.toml", "credenciais*", "credentials*",
    "memoria*.json", "memorias*.json", "lembretes*.json", "historico*.json",
    "conversas*.json", "cortex*.json", "auditoria*.jsonl", "*.log",
    "*.mp4", "*.mov", "*.mkv", "*.avi",
)

# Pastas que guardam dados do usuário e não devem subir inteiras.
PASTAS_PROIBIDAS: tuple[str, ...] = (
    "gravacoes", "gravações", "cameras_rec", "capturas", "backups", "backup",
    "dados_usuario", "user_data", "memoria", "memórias",
)

# --------------------------------------------------------------------------- segredos
# Cada regra: (rótulo, regex, marcador). A ordem importa: as mais específicas vêm antes.
_REGRAS: list[tuple[str, re.Pattern[str], str]] = [
    ("chave-privada",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----.*?"
                r"-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
                re.DOTALL), "<CHAVE_PRIVADA>"),
    ("openai", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}"), "<SUA_API_KEY>"),
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "<SUA_API_KEY>"),
    ("github-pat", re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "<SEU_GITHUB_TOKEN>"),
    ("github-pat2", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "<SEU_GITHUB_TOKEN>"),
    ("github-oauth", re.compile(r"\bgh[ours]_[A-Za-z0-9]{20,}"), "<SEU_GITHUB_TOKEN>"),
    ("google", re.compile(r"\bAIza[A-Za-z0-9_\-]{30,}"), "<SUA_API_KEY>"),
    ("groq", re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "<SUA_API_KEY>"),
    ("slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "<SEU_TOKEN>"),
    ("aws", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "<SUA_AWS_KEY>"),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.=]{20,}"), "Bearer <SEU_TOKEN>"),
    # atribuições genéricas: chave = "valor", token: valor, password=...
    ("atribuicao",
     re.compile(r"(?i)\b(api[_-]?key|apikey|secret|token|senha|password|passwd|pwd|"
                r"chave[_-]?api|chave|psk|wpa[_-]?psk|client[_-]?secret|access[_-]?token)"
                r"(\s*[=:]\s*)"
                r"(?P<v>\"[^\"\n]+\"|'[^'\n]+'|[^\s,;#]+)"),
     None),  # marcador calculado em _mascara_atribuicao
    ("mac",
     re.compile(r"\b(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b"), "<SEU_MAC>"),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<SEU_IP>"),
    ("home-win",
     re.compile(r"(?i)([A-Z]:\\Users\\)[^\\\s\"'/]+"), r"\1<USUARIO>"),
    ("home-nix", re.compile(r"(/home/)[^/\s\"':]+"), r"\1<USUARIO>"),
    ("home-mac", re.compile(r"(/Users/)[^/\s\"':]+"), r"\1<USUARIO>"),
]

# IPs que são seguros em código (loopback, "qualquer", documentação) e não devem ser mascarados.
_IPS_SEGUROS = frozenset({
    "0.0.0.0", "127.0.0.1", "255.255.255.255", "8.8.8.8", "8.8.4.4", "1.1.1.1",
})
# MACs genéricos usados em exemplos/código (broadcast, zeros).
_MACS_SEGUROS = frozenset({"ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"})
# Nomes de usuário genéricos que já são placeholders — não mascarar de novo.
_USUARIOS_SEGUROS = frozenset({"usuario", "usuário", "user", "<usuario>", "seu_usuario",
                               "public", "default", "all users", "todos"})


@dataclass
class Achado:
    """Um dado sensível encontrado em um texto."""

    tipo: str
    trecho: str
    linha: int = 0


@dataclass
class Relatorio:
    """Resultado de uma revisão: o que seria bloqueado e o que seria mascarado."""

    arquivos_bloqueados: list[str] = field(default_factory=list)
    achados: list[Achado] = field(default_factory=list)

    @property
    def seguro(self) -> bool:
        """Verdadeiro só quando nada seria vazado (nem arquivo proibido, nem segredo)."""
        return not self.arquivos_bloqueados and not self.achados

    def resumo(self) -> str:
        if self.seguro:
            return "Nenhum dado pessoal detectado. Seguro para versionar."
        partes = []
        if self.arquivos_bloqueados:
            partes.append(f"{len(self.arquivos_bloqueados)} arquivo(s) bloqueado(s): "
                          + ", ".join(self.arquivos_bloqueados[:10]))
        if self.achados:
            tipos: dict[str, int] = {}
            for a in self.achados:
                tipos[a.tipo] = tipos.get(a.tipo, 0) + 1
            partes.append("segredos: " + ", ".join(f"{t}×{n}" for t, n in tipos.items()))
        return " | ".join(partes)


# --------------------------------------------------------------------------- arquivos
def _glob_casa(nome: str, padrao: str) -> bool:
    return PurePosixPath(nome.lower()).match(padrao.lower())


def eh_arquivo_proibido(caminho: str) -> bool:
    """Diz se um caminho (relativo ao repositório) nunca pode subir automaticamente."""
    caminho = str(caminho).replace("\\", "/").strip()
    while caminho.startswith("./"):
        caminho = caminho[2:]
    if not caminho:
        return False
    nome = caminho.rsplit("/", 1)[-1]
    partes = {p.lower() for p in caminho.split("/")[:-1]}
    if partes & {p.lower() for p in PASTAS_PROIBIDAS}:
        return True
    return any(_glob_casa(nome, padrao) for padrao in ARQUIVOS_PROIBIDOS)


# --------------------------------------------------------------------------- segredos em texto
def _ip_sensivel(ip: str) -> bool:
    if ip in _IPS_SEGUROS:
        return False
    partes = ip.split(".")
    if len(partes) != 4:
        return False
    try:
        nums = [int(p) for p in partes]
    except ValueError:
        return False
    # octeto > 255 => não é IP de verdade (ex.: número de versão 1.2.3.400)
    return not any(n > 255 for n in nums)


def _mascara_atribuicao(m: re.Match[str]) -> str:
    chave, sep, valor = m.group(1), m.group(2), m.group("v")
    citado = valor[:1] in ("\"", "'")
    nu = valor.strip("\"'").strip()
    # valores obviamente vazios ou já-placeholder passam intactos
    if not nu or nu.startswith("<") or nu in ("''", '""') or nu.lower() in (
            "true", "false", "none", "null", "0", ""):
        return m.group(0)
    # valor sem aspas que parece código (variável, chamada, acesso a env) não é um segredo
    if not citado:
        if any(c in nu for c in ".()[]{}") or "environ" in nu.lower() or "getenv" in nu.lower():
            return m.group(0)
        if not re.fullmatch(r"[A-Za-z0-9/+_\-]{8,}", nu):
            return m.group(0)
    aspas = valor[0] if citado else ""
    rotulo = chave.lower()
    marcador = "<SUA_SENHA_WIFI>" if "psk" in rotulo or "wpa" in rotulo else \
        "<SUA_SENHA>" if "senha" in rotulo or "pass" in rotulo or "pwd" in rotulo else \
        "<SEU_TOKEN>" if "token" in rotulo else "<SUA_API_KEY>"
    return f"{chave}{sep}{aspas}{marcador}{aspas}"


def _aplicar_regra(rotulo: str, regex: re.Pattern[str], marcador, texto: str,
                   coletar: list[Achado] | None) -> str:
    def troca(m: re.Match[str]) -> str:
        bruto = m.group(0)
        if rotulo == "ipv4" and not _ip_sensivel(bruto):
            return bruto
        if rotulo == "mac" and bruto.lower() in _MACS_SEGUROS:
            return bruto
        if rotulo in ("home-win", "home-nix", "home-mac"):
            usuario = bruto.split("\\")[-1] if rotulo == "home-win" else bruto.rsplit("/", 1)[-1]
            if usuario.lower() in _USUARIOS_SEGUROS:
                return bruto
        if rotulo == "atribuicao":
            resultado = _mascara_atribuicao(m)
            if resultado == bruto:
                return bruto
            if coletar is not None:
                coletar.append(Achado(rotulo, bruto))
            return resultado
        if coletar is not None:
            coletar.append(Achado(rotulo, bruto))
        if isinstance(marcador, str) and "\\1" in marcador:
            return regex.sub(marcador, bruto)
        return marcador

    return regex.sub(troca, texto)


def achados(texto: str) -> list[Achado]:
    """Lista os dados sensíveis encontrados, sem alterar o texto."""
    encontrados: list[Achado] = []
    _mascarar(texto, encontrados)
    return encontrados


def _mascarar(texto: str, coletar: list[Achado] | None) -> str:
    for rotulo, regex, marcador in _REGRAS:
        texto = _aplicar_regra(rotulo, regex, marcador, texto, coletar)
    return texto


def mascarar(texto: str) -> str:
    """Devolve o texto com todos os dados sensíveis trocados por marcadores genéricos."""
    return _mascarar(texto, None)


# --------------------------------------------------------------------------- diffs e árvores
_CAB_ARQUIVO = re.compile(r"^\+\+\+ b/(.+)$")


def revisar_diff(diff: str) -> Relatorio:
    """Revisa um diff unificado (`git diff`): bloqueia arquivos proibidos e acha segredos.

    Só as linhas adicionadas (começando com `+`, menos o cabeçalho `+++`) são inspecionadas,
    porque são elas que entrariam no commit.
    """
    rel = Relatorio()
    arquivo_atual = ""
    linha_num = 0
    for linha in diff.splitlines():
        cab = _CAB_ARQUIVO.match(linha)
        if cab:
            arquivo_atual = cab.group(1).strip()
            if arquivo_atual != "/dev/null" and eh_arquivo_proibido(arquivo_atual):
                rel.arquivos_bloqueados.append(arquivo_atual)
            linha_num = 0
            continue
        if linha.startswith("@@"):
            m = re.search(r"\+(\d+)", linha)
            linha_num = (int(m.group(1)) if m else 1) - 1
            continue
        if linha.startswith("+") and not linha.startswith("+++"):
            linha_num += 1
            if arquivo_atual and eh_arquivo_proibido(arquivo_atual):
                continue  # já bloqueado inteiro; não precisa listar cada segredo
            for ach in achados(linha[1:]):
                ach.linha = linha_num
                rel.achados.append(ach)
        elif not linha.startswith("-"):
            linha_num += 1
    return rel


def revisar_arquivos(arquivos: dict[str, str]) -> Relatorio:
    """Revisa um conjunto {caminho: conteúdo} como se fossem adicionados por inteiro."""
    rel = Relatorio()
    for caminho, conteudo in arquivos.items():
        if eh_arquivo_proibido(caminho):
            rel.arquivos_bloqueados.append(caminho)
            continue
        for ach in achados(conteudo):
            rel.achados.append(ach)
    return rel
