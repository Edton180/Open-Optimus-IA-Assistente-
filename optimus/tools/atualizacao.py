"""Ferramentas de autoatualização pelo GitHub, com barreira de privacidade.

Correspondem aos botões do painel ("🔄 Verificar/Baixar Atualizações") e a comandos de voz
("Optimus, veja se tem atualização"). O envio para o GitHub (`git push`) continua sendo um
passo manual e explícito — nunca roda sozinho — e também passa pela barreira de privacidade.
"""

from __future__ import annotations

from pathlib import Path

from optimus import autoatualizar, privacy_guard
from optimus.safety import CRITICO, LIVRE
from optimus.tools.base import Contexto, ferramenta, texto
from optimus.updater import Atualizador, ErroGit


def _raiz_repo(ctx: Contexto) -> Path:
    """Pasta do programa: config [atualizacao].repo, senão onde o pacote está instalado."""
    return autoatualizar.pasta_programa(getattr(ctx, "config", None) if ctx else None)


@ferramenta(
    "atualizacao_verificar",
    "Verifica se há uma versão mais nova do Optimus no GitHub, sem baixar nada. Seus dados "
    "locais (memórias, chaves, config) ficam fora da pasta do programa e são sempre "
    "preservados.",
    {}, grupo="controle", risco=LIVRE,
)
def atualizacao_verificar(ctx):
    return autoatualizar.verificar(getattr(ctx, "config", None))


@ferramenta(
    "atualizacao_baixar",
    "Baixa e aplica a atualização mais recente do Optimus, sem perder dados locais: num clone "
    "do Git faz git pull seguro; instalado sem Git baixa a release do GitHub, confere o "
    "SHA-256 e guarda uma cópia da versão atual para poder voltar.",
    {}, grupo="controle", risco=CRITICO,
)
def atualizacao_baixar(ctx):
    return autoatualizar.baixar(getattr(ctx, "config", None))


@ferramenta(
    "atualizacao_voltar",
    "Desfaz a última atualização do Optimus e volta para a versão anterior.",
    {}, grupo="controle", risco=CRITICO,
)
def atualizacao_voltar(ctx):
    return autoatualizar.voltar(getattr(ctx, "config", None))


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
