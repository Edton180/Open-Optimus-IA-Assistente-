"""Autoatualização bidirecional com o GitHub, sem perder dados e sem vazar nada pessoal.

Dois sentidos:

1. **Baixar** (`verificar`/`atualizar`): checa se há commits novos no repositório oficial e
   faz um `git pull --ff-only`. Os dados do usuário (config, memórias, banco, chaves,
   modelos) ficam em `OPTIMUS_HOME` — **fora** da árvore do Git — então o pull nunca os
   toca. Antes de atualizar, o estado da árvore de trabalho é verificado: se houver
   mudanças locais não salvas, a atualização para e avisa, em vez de sobrescrever.

2. **Subir** (`preparar`/`commit`): quando o Optimus cria/corrige código para si mesmo, o
   usuário pode enviar ao GitHub. **Regra crítica:** todo commit automático passa primeiro
   pelo `privacy_guard`. Se o diff preparado contiver um arquivo proibido ou qualquer
   segredo (chave de API, token, IP, MAC, senha de Wi-Fi, caminho com nome do usuário), o
   commit é **recusado** e o `staging` é desfeito. Nada vaza sem o usuário ver o relatório.

O `push` nunca é automático: é um passo separado e explícito (`push`), que também só roda
depois de uma revisão limpa.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from optimus import privacy_guard

REPO_OFICIAL = "https://github.com/Edton180/Open-Optimus-IA-Assistente-"


class ErroGit(RuntimeError):
    """Falha ao rodar um comando git (git ausente, pasta não é repositório, etc.)."""


@dataclass
class Estado:
    ramo: str
    commit_local: str
    limpa: bool
    atras: int = 0   # commits que faltam baixar
    frente: int = 0  # commits locais ainda não enviados

    @property
    def atualizado(self) -> bool:
        return self.atras == 0


class Atualizador:
    """Operações de atualização sobre um repositório Git local."""

    def __init__(self, repo: str | Path | None = None):
        self.repo = Path(repo or Path.cwd()).resolve()

    # ------------------------------------------------------------------ git cru
    def _git(self, *args: str, verificar: bool = False, tempo: int = 60) -> subprocess.CompletedProcess:
        try:
            r = subprocess.run(
                ["git", "-C", str(self.repo), *args],
                capture_output=True, text=True, timeout=tempo, check=False,
            )
        except FileNotFoundError as erro:
            raise ErroGit("O Git não está instalado neste PC.") from erro
        except subprocess.TimeoutExpired as erro:
            raise ErroGit(f"O comando git demorou demais: git {' '.join(args)}") from erro
        if verificar and r.returncode != 0:
            raise ErroGit((r.stderr or r.stdout).strip() or f"git {' '.join(args)} falhou")
        return r

    def eh_repositorio(self) -> bool:
        r = self._git("rev-parse", "--is-inside-work-tree")
        return r.returncode == 0 and r.stdout.strip() == "true"

    # ------------------------------------------------------------------ estado / baixar
    def estado(self, remoto: str = "origin") -> Estado:
        if not self.eh_repositorio():
            raise ErroGit(f"{self.repo} não é um repositório Git.")
        ramo = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "HEAD"
        local = self._git("rev-parse", "HEAD").stdout.strip()
        limpa = not self._git("status", "--porcelain").stdout.strip()
        atras = frente = 0
        self._git("fetch", remoto, "--quiet", tempo=120)
        contagem = self._git("rev-list", "--left-right", "--count",
                             f"HEAD...{remoto}/{ramo}")
        if contagem.returncode == 0 and contagem.stdout.strip():
            try:
                frente_s, atras_s = contagem.stdout.split()
                frente, atras = int(frente_s), int(atras_s)
            except ValueError:
                pass
        return Estado(ramo=ramo, commit_local=local, limpa=limpa, atras=atras, frente=frente)

    def verificar(self, remoto: str = "origin") -> dict:
        """Diz se há atualização disponível, sem mudar nada."""
        est = self.estado(remoto)
        if est.atualizado:
            msg = "O Optimus já está na versão mais recente."
        else:
            msg = (f"Há {est.atras} atualização(ões) disponível(is) no GitHub. "
                   "Seus dados locais (memórias, chaves, config) ficam fora do Git e serão "
                   "preservados.")
        return {"atualizado": est.atualizado, "atras": est.atras, "frente": est.frente,
                "ramo": est.ramo, "limpa": est.limpa, "mensagem": msg}

    def atualizar(self, remoto: str = "origin") -> dict:
        """Baixa os commits novos com `pull --ff-only`, preservando os dados locais."""
        est = self.estado(remoto)
        if est.atualizado:
            return {"ok": True, "mudou": False, "mensagem": "Já estava atualizado."}
        if not est.limpa:
            return {"ok": False, "mudou": False,
                    "erro": "Há mudanças locais não salvas. Faça commit ou descarte antes de "
                            "atualizar, para não perder nada."}
        r = self._git("pull", "--ff-only", remoto, est.ramo, tempo=180)
        if r.returncode != 0:
            return {"ok": False, "mudou": False,
                    "erro": "Não deu para atualizar sem conflito (pull --ff-only): "
                            + (r.stderr or r.stdout).strip()}
        return {"ok": True, "mudou": True,
                "mensagem": f"Atualizado para a versão mais recente do ramo {est.ramo}."}

    # ------------------------------------------------------------------ subir (com barreira)
    def _diff_preparado(self) -> str:
        return self._git("diff", "--cached").stdout

    def preparar(self, arquivos: list[str] | None = None) -> tuple[privacy_guard.Relatorio, str]:
        """Faz o `staging` e devolve (relatório de privacidade, diff). Não commita.

        Se o relatório não for seguro, o `staging` é **desfeito** antes de retornar, para que
        nada sensível fique pronto para commit por engano.
        """
        if not self.eh_repositorio():
            raise ErroGit(f"{self.repo} não é um repositório Git.")
        self._git("reset", "--quiet")  # começa limpo
        if arquivos:
            self._git("add", "--", *arquivos)
        else:
            self._git("add", "-A")
        diff = self._diff_preparado()
        relatorio = privacy_guard.revisar_diff(diff)
        if not relatorio.seguro:
            self._git("reset", "--quiet")  # barreira: não deixa nada sensível no staging
        return relatorio, diff

    def commit(self, mensagem: str, arquivos: list[str] | None = None) -> dict:
        """Prepara, revisa e só então commita. Recusa se houver risco de vazamento."""
        if not mensagem.strip():
            return {"ok": False, "erro": "A mensagem de commit não pode ficar vazia."}
        relatorio, diff = self.preparar(arquivos)
        if not diff.strip():
            return {"ok": False, "erro": "Não há mudanças preparadas para commit."}
        if not relatorio.seguro:
            return {"ok": False, "bloqueado_por_privacidade": True,
                    "relatorio": relatorio.resumo(),
                    "arquivos_bloqueados": relatorio.arquivos_bloqueados,
                    "erro": "Commit recusado pela barreira de privacidade. " + relatorio.resumo()}
        r = self._git("commit", "-m", mensagem)
        if r.returncode != 0:
            return {"ok": False, "erro": (r.stderr or r.stdout).strip()}
        commit = self._git("rev-parse", "HEAD").stdout.strip()[:10]
        return {"ok": True, "commit": commit,
                "mensagem": f"Commit {commit} criado. Revisão de privacidade: limpa."}

    def push(self, remoto: str = "origin", ramo: str | None = None) -> dict:
        """Envia os commits. Passo explícito: nunca roda sozinho no commit."""
        est = self.estado(remoto)
        if est.frente == 0:
            return {"ok": True, "enviado": False, "mensagem": "Nada novo para enviar."}
        # Rede antifalha: revisa o que será enviado uma última vez.
        diff = self._git("diff", f"{remoto}/{est.ramo}...HEAD").stdout
        relatorio = privacy_guard.revisar_diff(diff)
        if not relatorio.seguro:
            return {"ok": False, "bloqueado_por_privacidade": True,
                    "erro": "Push recusado pela barreira de privacidade. " + relatorio.resumo()}
        r = self._git("push", remoto, ramo or est.ramo, tempo=180)
        if r.returncode != 0:
            return {"ok": False, "erro": (r.stderr or r.stdout).strip()}
        return {"ok": True, "enviado": True,
                "mensagem": f"{est.frente} commit(s) enviado(s) para {remoto}/{ramo or est.ramo}."}
