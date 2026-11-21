"""Um só ponto de entrada para atualizar o Optimus, seja qual for a forma de instalação.

- **Clone do Git** → `updater.Atualizador` (`git pull --ff-only`, voltar com `reset --keep`).
- **Instalado sem Git** (pip, ZIP, instalador) → `releases` (Releases do GitHub com SHA-256,
  cópia de segurança e voltar).

Usado pelas ferramentas de voz/painel, pelo comando `optimus atualizar` e pela verificação
automática ao iniciar.
"""

from __future__ import annotations

import logging
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
        saida = decidir(config).para_dict()
        saida["modo"] = "release"
        return saida
    except (ErroGit, releases.ErroRelease) as erro:
        return {"erro": str(erro)}


def baixar(config) -> dict:
    """Aplica a atualização (quem chama já pediu confirmação ao usuário)."""
    git = _git(config)
    try:
        if git:
            return git.atualizar()
        decisao = decidir(config)
        if not decisao.alvo:
            return {"ok": True, "mudou": False, "mensagem": decisao.mensagem()}
        return releases.instalar(decisao.alvo, pasta_programa(config), optimus.__version__)
    except (ErroGit, releases.ErroRelease) as erro:
        return {"ok": False, "erro": str(erro)}


def voltar(config) -> dict:
    git = _git(config)
    try:
        return git.voltar() if git else releases.voltar()
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
        decisao = decidir(config)
        if not decisao.alvo:
            return None
        if decisao.instalar_sozinho:
            return releases.instalar(decisao.alvo, pasta_programa(config), optimus.__version__)
        return decisao.para_dict()
    except Exception as erro:  # noqa: BLE001 - nunca atrapalha a abertura do Optimus
        log.info("Verificação automática de atualização falhou: %s", erro)
        return None
