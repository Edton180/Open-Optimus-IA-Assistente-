"""Ferramentas de autoatualização pelo GitHub, com barreira de privacidade.

Correspondem aos botões do painel ("🔄 Verificar/Baixar Atualizações") e a comandos de voz
("Optimus, veja se tem atualização"). O envio para o GitHub (`git push`) continua sendo um
passo manual e explícito — nunca roda sozinho — e também passa pela barreira de privacidade.
"""

from __future__ import annotations

from pathlib import Path

import optimus
from optimus import privacy_guard
from optimus.safety import CRITICO, LIVRE
from optimus.tools.base import Contexto, ferramenta, texto
from optimus.updater import Atualizador, ErroGit


def _raiz_repo(ctx: Contexto) -> Path:
    """Descobre a pasta do repositório: config [atualizacao].repo, senão o pacote instalado."""
    if ctx and getattr(ctx, "config", None):
        configurado = ctx.config.get("atualizacao", "repo", "")
        if configurado:
            return Path(configurado).expanduser()
    return Path(optimus.__file__).resolve().parent.parent


@ferramenta(
    "atualizacao_verificar",
    "Verifica se há uma versão mais nova do Optimus no GitHub, sem baixar nada. Seus dados "
    "locais (memórias, chaves, config) ficam fora do Git e são sempre preservados.",
    {}, grupo="controle", risco=LIVRE,
)
def atualizacao_verificar(ctx):
    try:
        return Atualizador(_raiz_repo(ctx)).verificar()
    except ErroGit as erro:
        return {"erro": str(erro)}


@ferramenta(
    "atualizacao_baixar",
    "Baixa e aplica a atualização mais recente do Optimus (git pull seguro, sem perder dados "
    "locais). Só avança se não houver mudanças locais não salvas.",
    {}, grupo="controle", risco=CRITICO,
)
def atualizacao_baixar(ctx):
    try:
        return Atualizador(_raiz_repo(ctx)).atualizar()
    except ErroGit as erro:
        return {"erro": str(erro)}


@ferramenta(
    "privacidade_revisar",
    "Mostra o que a barreira de privacidade bloquearia antes de um envio ao GitHub: arquivos "
    "sensíveis e segredos (chaves, tokens, IPs, senhas) que seriam mascarados.",
    {"texto": texto("Texto ou diff a revisar (opcional). Vazio = revisa o que está preparado "
                    "no Git local)")},
    grupo="controle", risco=LIVRE, obrigatorios=[],
)
def privacidade_revisar(ctx, texto: str = ""):
    if texto and texto.strip():
        rel = privacy_guard.revisar_diff(texto) if texto.lstrip().startswith(
            ("diff ", "--- ", "+++ ")) else privacy_guard.revisar_arquivos({"entrada": texto})
    else:
        try:
            rel, _ = Atualizador(_raiz_repo(ctx)).preparar()
        except ErroGit as erro:
            return {"erro": str(erro)}
    return {"seguro": rel.seguro, "resumo": rel.resumo(),
            "arquivos_bloqueados": rel.arquivos_bloqueados,
            "segredos": [{"tipo": a.tipo, "linha": a.linha} for a in rel.achados]}
