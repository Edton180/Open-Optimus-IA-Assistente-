"""Um só ponto de entrada para atualizar o Optimus, seja qual for a forma de instalação.

- **Clone do Git** → `updater.Atualizador` (`git pull --ff-only`, voltar com `reset --keep`).
- **Instalado sem Git** (pip, ZIP, instalador) → `releases` (Releases do GitHub com SHA-256,
  cópia de segurança e voltar).

Usado pelas ferramentas de voz/painel, pelo comando `optimus atualizar` e pela verificação
automática ao iniciar.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import optimus
from optimus import releases
from optimus.updater import Atualizador, ErroGit

log = logging.getLogger(__name__)


def pasta_programa(config=None) -> Path:
    """Pasta que contém o pacote `optimus/` (raiz do clone ou site-packages)."""
    if config is not None:
        configurado = config.get("atualizacao", "repo", "")
        if configurado:
            return Path(configurado).expanduser()
    return Path(optimus.__file__).resolve().parent.parent


def _git(config) -> Atualizador | None:
    at = Atualizador(pasta_programa(config))
    try:
        return at if at.eh_repositorio() else None
    except ErroGit:  # Git não instalado: segue pelas releases
        return None


def _repo_github(config) -> str:
    return (config.get("atualizacao", "github", "") if config else "") or releases.REPO_PADRAO


def decidir(config, agora: datetime | None = None, lista=None) -> releases.Decisao:
    lista = lista if lista is not None else releases.listar(_repo_github(config))
    return releases.decidir(optimus.__version__, lista, releases.Politica.da_config(config),
                            agora=agora)


def verificar(config) -> dict:
    """Só olha. Não muda nada."""
    git = _git(config)
    try:
        if git:
            saida = git.verificar()
            saida["modo"] = "git"
            return saida
        try:
            decisao = decidir(config)
        except releases.ErroRelease:
            decisao = None
        if decisao and decisao.alvo:
            saida = decisao.para_dict()
            saida["modo"] = "release"
            saida["atualizado"] = False
            return saida
        # Sem release mais nova publicada: compara o commit instalado com o da main.
        return verificar_github(config)
    except (ErroGit, releases.ErroRelease) as erro:
        return {"erro": str(erro)}


def baixar(config) -> dict:
    """Aplica a atualização (quem chama já pediu confirmação ao usuário)."""
    git = _git(config)
    try:
        if git:
            return git.atualizar()
        try:
            decisao = decidir(config)
        except releases.ErroRelease:
            decisao = None
        if decisao and decisao.alvo:
            return _por_release(decisao, config)
        return baixar_github(config)
    except (ErroGit, releases.ErroRelease) as erro:
        return {"ok": False, "erro": str(erro)}


def _por_release(decisao, config) -> dict:
    resultado = releases.instalar(decisao.alvo, pasta_programa(config), optimus.__version__)
    if resultado.get("ok", True):
        _marcar_modo("release")
    return resultado


def _marcar_modo(modo: str) -> None:
    dados = _ler_registro()
    dados["ultimo_modo"] = modo
    _registro().parent.mkdir(parents=True, exist_ok=True)
    _registro().write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def voltar(config) -> dict:
    git = _git(config)
    try:
        if git:
            return git.voltar()
        # Desfaz a atualização mais recente, seja por release ou pelo commit do GitHub.
        if _ler_registro().get("ultimo_modo") != "github" \
                and (releases._pasta_backups() / "ultima.json").exists():
            return releases.voltar()
        return voltar_github(config)
    except (ErroGit, releases.ErroRelease, OSError) as erro:
        return {"ok": False, "erro": str(erro)}


def automatico(config) -> dict | None:
    """Rodado ao iniciar (se `[atualizacao] ao_iniciar`). Devolve um aviso para mostrar.

    Só instala sozinho quando: é instalação por release, `automatico = true`, a versão nova
    não é maior, já passou o tempo de espera e está dentro da janela. Num clone do Git só avisa
    (quem desenvolve decide quando dar pull).
    """
    if not config.get("atualizacao", "ao_iniciar", False):
        return None
    try:
        if _git(config):
            info = verificar(config)
            return info if info.get("atras") else None
        try:
            decisao = decidir(config)
        except releases.ErroRelease:
            decisao = None
        if decisao is None or not decisao.alvo:
            # Sem release mais nova: compara com o último commit do GitHub e só avisa.
            info = verificar_github(config)
            return info if info.get("disponivel") else None
        if decisao.instalar_sozinho:
            return _por_release(decisao, config)
        return decisao.para_dict()
    except Exception as erro:  # noqa: BLE001 - nunca atrapalha a abertura do Optimus
        log.info("Verificação automática de atualização falhou: %s", erro)
        return None


# ---------------------------------------------------------------------- modo "github"
# Reserva para quem instalou sem Git (instalador/pip) quando não há release mais nova
# publicada: segue o último commit do ramo principal. O pip baixa o ZIP oficial do GitHub
# (codeload.github.com, por HTTPS), reinstala o pacote e instala dependências novas. Os dados
# do usuário ficam em OPTIMUS_HOME e não são tocados.

def _registro() -> Path:
    from optimus.config import pasta_base

    return pasta_base() / "atualizacao.json"


def _ler_registro() -> dict:
    try:
        return json.loads(_registro().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def registrar_commit(sha: str, anterior: str | None = None) -> None:
    """Guarda qual commit está instalado (o instalador chama isto ao terminar)."""
    sha = (sha or "").strip()
    if not sha:
        return
    dados = _ler_registro()
    dados["anterior"] = anterior if anterior is not None else dados.get("commit", "")
    dados["commit"] = sha
    dados["quando"] = datetime.now().isoformat(timespec="seconds")
    _registro().parent.mkdir(parents=True, exist_ok=True)
    _registro().write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def commit_instalado() -> str:
    return _ler_registro().get("commit", "")


def _ramo(config) -> str:
    return (config.get("atualizacao", "ramo", "") if config else "") or "main"


def _commit_remoto_atom(repo: str, ramo: str) -> dict:
    """Consulta o feed público quando a API REST está limitada (403/429/5xx)."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    import httpx

    url = f"https://github.com/{repo}/commits/{quote(ramo, safe='/')}.atom"
    r = httpx.get(url, timeout=15, follow_redirects=True,
                  headers={"User-Agent": "open-optimus-updater"})
    r.raise_for_status()
    raiz = ET.fromstring(r.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entrada = raiz.find("atom:entry", ns)
    if entrada is None:
        raise ValueError("O feed do GitHub não contém commits.")
    identificador = entrada.findtext("atom:id", default="", namespaces=ns)
    # O feed usa tag:github.com,2008:Grit::Commit/<SHA>.
    sha = identificador.rsplit("/", 1)[-1].strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise ValueError("O GitHub não informou um SHA de commit válido.")
    titulo = entrada.findtext("atom:title", default="", namespaces=ns).strip()
    atualizado = entrada.findtext("atom:updated", default="", namespaces=ns)
    return {"sha": sha, "data": atualizado[:10], "titulo": titulo[:120]}


def _commit_remoto_padrao(repo: str, ramo: str) -> dict:
    import httpx

    try:
        r = httpx.get(f"https://api.github.com/repos/{repo}/commits/{ramo}", timeout=15,
                      follow_redirects=True,
                      headers={"Accept": "application/vnd.github+json",
                               "User-Agent": "open-optimus-updater"})
        r.raise_for_status()
        dado = r.json()
        commit = dado.get("commit") or {}
        return {"sha": dado.get("sha", ""),
                "data": ((commit.get("committer") or {}).get("date") or "")[:10],
                "titulo": (commit.get("message") or "").splitlines()[0][:120]
                if commit.get("message") else ""}
    except httpx.HTTPStatusError as erro:
        # GitHub pode limitar a API REST mesmo quando o repositório está público.
        if erro.response.status_code not in (403, 429, 500, 502, 503, 504):
            raise
        try:
            return _commit_remoto_atom(repo, ramo)
        except Exception:
            # Mantém a exceção original para que a interface informe o erro HTTP real.
            raise erro


def _pip_padrao(url: str) -> tuple[int, str]:
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    saidas = []
    # 1) troca o pacote mesmo com o mesmo número de versão; 2) instala dependências novas.
    for extra in (["--upgrade", "--force-reinstall", "--no-deps"], ["--upgrade"]):
        r = subprocess.run(base + extra + [url], capture_output=True, text=True,
                           timeout=1200, check=False)
        saidas.append((r.stdout or "") + (r.stderr or ""))
        if r.returncode != 0:
            return r.returncode, "\n".join(saidas)
    return 0, "\n".join(saidas)


# Pontos de troca para os testes (sem rede, sem pip de verdade).
_commit_remoto = _commit_remoto_padrao
_pip = _pip_padrao


def _url_zip(repo: str, ref: str) -> str:
    # Com os extras "completo", o pip também instala dependências opcionais novas.
    return f"optimus-assistente[completo] @ https://codeload.github.com/{repo}/zip/{ref}"


def verificar_github(config) -> dict:
    repo, ramo = _repo_github(config), _ramo(config)
    try:
        remoto = _commit_remoto(repo, ramo)
    except Exception as erro:  # noqa: BLE001 - sem internet, GitHub fora do ar, limite da API
        return {"erro": "Não consegui falar com o GitHub para ver se há atualização. Confira "
                        f"a internet e tente de novo. ({type(erro).__name__})"}
    sha, local = remoto.get("sha", ""), commit_instalado()
    curto = sha[:7]
    if local and local == sha:
        return {"modo": "github", "atualizado": True, "disponivel": False, "commit": curto,
                "mensagem": f"O Optimus já está na versão mais recente (commit {curto})."}
    quando = f" de {remoto['data']}" if remoto.get("data") else ""
    titulo = f": {remoto['titulo']}" if remoto.get("titulo") else ""
    if local:
        msg = (f"Há uma versão nova no GitHub (commit {curto}{quando}{titulo}). Você usa o "
               f"commit {local[:7]}.")
    else:
        msg = (f"A versão mais recente no GitHub é o commit {curto}{quando}{titulo}. Não sei "
               "qual versão está instalada aqui, então posso baixar essa agora.")
    return {"modo": "github", "atualizado": False, "disponivel": True, "commit": curto,
            "mensagem": msg + " Suas memórias, chaves e configurações ficam preservadas."}


def baixar_github(config) -> dict:
    repo, ramo = _repo_github(config), _ramo(config)
    try:
        sha = _commit_remoto(repo, ramo).get("sha", "")
    except Exception as erro:  # noqa: BLE001
        return {"ok": False, "erro": "Não consegui falar com o GitHub para baixar a "
                                     f"atualização. Confira a internet. ({type(erro).__name__})"}
    if not sha:
        return {"ok": False, "erro": "O GitHub não informou a versão mais recente."}
    anterior = commit_instalado()
    if sha == anterior:
        return {"ok": True, "mudou": False, "mensagem": "Já estava na versão mais recente."}
    codigo, saida = _pip(_url_zip(repo, sha))
    if codigo != 0:
        detalhe = saida.strip()[-500:]
        # A primeira etapa do pip pode já ter substituído os arquivos do pacote antes de
        # falhar na instalação das dependências. Quando há um commit anterior registrado,
        # tenta restaurá-lo automaticamente para não deixar uma instalação parcial.
        if anterior and anterior != sha:
            codigo_volta, saida_volta = _pip(_url_zip(repo, anterior))
            if codigo_volta == 0:
                return {"ok": False, "restaurado": True,
                        "erro": "A atualização falhou e a versão anterior foi restaurada "
                                "automaticamente. Detalhe: " + detalhe}
            return {"ok": False, "restaurado": False,
                    "erro": "A atualização falhou e a restauração automática também falhou. "
                            "Não abra o Optimus até reparar a instalação. Atualização: "
                            + detalhe + " | Restauração: " + saida_volta.strip()[-500:]}
        return {"ok": False, "erro": "A atualização falhou. Não havia commit anterior "
                                     "registrado para restauração automática. Detalhe: "
                                     + detalhe}
    registrar_commit(sha)
    _marcar_modo("github")
    return {"ok": True, "mudou": True, "modo": "github", "commit": sha[:7],
            "mensagem": f"Optimus atualizado para o commit {sha[:7]}. Reinicie o Optimus para "
                        "usar a nova versão. Se algo der errado, use \"Voltar versão\"."}

def voltar_github(config) -> dict:
    dados = _ler_registro()
    anterior = dados.get("anterior", "")
    if not anterior:
        return {"ok": False, "erro": "Não há atualização para desfazer."}
    codigo, saida = _pip(_url_zip(_repo_github(config), anterior))
    if codigo != 0:
        return {"ok": False, "erro": "Não consegui voltar a versão. Detalhe: "
                                     + saida.strip()[-500:]}
    registrar_commit(anterior, anterior="")
    return {"ok": True, "mudou": True, "commit": anterior[:7],
            "mensagem": f"Voltei para o commit {anterior[:7]}. Reinicie o Optimus."}
