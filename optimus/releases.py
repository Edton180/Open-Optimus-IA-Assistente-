"""Atualização pelas *Releases* do GitHub, para quem instalou o Optimus sem Git.

Quem usa um clone do Git continua com o `updater.py` (`git pull --ff-only`). Quem instalou
por pip, ZIP ou instalador usa este módulo:

1. **Decidir** (`decidir`): olha as releases publicadas e escolhe a mais nova que serve para
   o canal (estável ou beta). É uma função pura, sem rede, para dar para testar e simular.
   Regras:
   - rascunhos nunca entram; pré-lançamentos só no canal beta;
   - versão **maior** nova (1.x → 2.x) nunca é automática: sempre pede o seu "sim";
   - depois de publicada, a release espera `espera_horas` antes de ser aplicada sozinha
     (se ela tiver um defeito, dá tempo de sair a correção);
   - a instalação automática só roda dentro da janela de horário (ex.: "02:00-05:00").
2. **Instalar** (`instalar`): baixa o pacote, confere o SHA-256 publicado junto
   (`SHA256SUMS`), guarda uma cópia da versão atual e só então troca os arquivos.
3. **Voltar** (`voltar`): desfaz a última atualização usando a cópia guardada.

Os dados do usuário ficam em `OPTIMUS_HOME`, fora da pasta do programa: nada disso os toca.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_PADRAO = "Edton180/Open-Optimus-IA-Assistente-"
API = "https://api.github.com/repos/{repo}/releases"
NOME_SOMAS = "SHA256SUMS"

_VERSAO = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.]?([0-9A-Za-z.-]+))?$")


class ErroRelease(RuntimeError):
    """Falha ao consultar, baixar, conferir ou instalar uma release."""


# ---------------------------------------------------------------------- versões
@dataclass(frozen=True)
class Versao:
    maior: int
    menor: int = 0
    correcao: int = 0
    pre: str = ""  # "beta.1", "rc2"... vazio = estável

    @classmethod
    def ler(cls, texto: str) -> Versao:
        m = _VERSAO.match((texto or "").strip())
        if not m:
            raise ValueError(f"Versão inválida: {texto!r}")
        return cls(int(m[1]), int(m[2] or 0), int(m[3] or 0), m[4] or "")

    def _chave(self) -> tuple:
        # Estável vem depois de qualquer pré-lançamento da mesma versão (1.0.0-beta < 1.0.0).
        partes = tuple((0, int(p)) if p.isdigit() else (1, p)
                       for p in re.split(r"[.-]", self.pre)) if self.pre else ()
        return (self.maior, self.menor, self.correcao, 0 if self.pre else 1, partes)

    def __lt__(self, outra: Versao) -> bool:
        return self._chave() < outra._chave()

    def __le__(self, outra: Versao) -> bool:
        return self._chave() <= outra._chave()

    def __gt__(self, outra: Versao) -> bool:
        return self._chave() > outra._chave()

    def __ge__(self, outra: Versao) -> bool:
        return self._chave() >= outra._chave()

    def __str__(self) -> str:
        base = f"{self.maior}.{self.menor}.{self.correcao}"
        return f"{base}-{self.pre}" if self.pre else base


# ---------------------------------------------------------------------- releases
@dataclass
class Release:
    tag: str
    versao: Versao
    publicada: datetime
    prerelease: bool = False
    draft: bool = False
    notas: str = ""
    zip_url: str = ""
    assets: dict[str, str] = field(default_factory=dict)  # nome -> url de download

    @classmethod
    def de_api(cls, dado: dict[str, Any]) -> Release | None:
        """Converte um item da API do GitHub. Devolve None se a tag não for uma versão."""
        try:
            versao = Versao.ler(dado.get("tag_name", ""))
        except ValueError:
            return None
        quando = dado.get("published_at") or dado.get("created_at") or "1970-01-01T00:00:00Z"
        assets = {a.get("name", ""): a.get("browser_download_url", "")
                  for a in dado.get("assets") or [] if a.get("name")}
        return cls(tag=dado.get("tag_name", ""), versao=versao, publicada=_data(quando),
                   prerelease=bool(dado.get("prerelease")), draft=bool(dado.get("draft")),
                   notas=(dado.get("body") or "").strip(),
                   zip_url=dado.get("zipball_url") or "", assets=assets)

    def pacote(self) -> tuple[str, str]:
        """(nome, url) do ZIP do programa publicado na release (optimus-*.zip)."""
        for nome, url in self.assets.items():
            if nome.lower().startswith("optimus") and nome.lower().endswith(".zip"):
                return nome, url
        return "", ""


def _data(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(timezone.utc)


def listar(repo: str = REPO_PADRAO, cliente=None, tempo: float = 20) -> list[Release]:
    """Busca as releases do repositório no GitHub (só leitura, sem token)."""
    import httpx

    dono = cliente or httpx.Client(timeout=tempo, follow_redirects=True,
                                   headers={"Accept": "application/vnd.github+json",
                                            "User-Agent": "open-optimus-updater"})
    try:
        r = dono.get(API.format(repo=repo), params={"per_page": 30})
        r.raise_for_status()
        dados = r.json()
    except Exception as erro:
        raise ErroRelease(f"Não consegui consultar as releases no GitHub: {erro}") from erro
    finally:
        if cliente is None:
            dono.close()
    return [rel for item in dados if (rel := Release.de_api(item))]


# ---------------------------------------------------------------------- decisão
@dataclass
class Politica:
    canal: str = "estavel"        # estavel | beta
    automatico: bool = False      # instalar sozinho (só versões menores e de correção)
    espera_horas: float = 48      # tempo de espera depois de publicada
    janela: str = ""              # "02:00-05:00" (vazio = qualquer hora)

    @classmethod
    def da_config(cls, config) -> Politica:
        def g(chave, padrao):
            return config.get("atualizacao", chave, padrao) if config else padrao

        return cls(canal=str(g("canal", "estavel")).lower(),
                   automatico=bool(g("automatico", False)),
                   espera_horas=float(g("espera_horas", 48)),
                   janela=str(g("janela", "") or ""))


@dataclass
class Decisao:
    atual: str
    alvo: Release | None
    motivo: str          # atualizado | disponivel | aguardando | fora_da_janela | versao_maior
    instalar_sozinho: bool = False
    pede_confirmacao: bool = False

    @property
    def disponivel(self) -> bool:
        return self.alvo is not None

    def mensagem(self) -> str:
        if not self.alvo:
            return f"O Optimus já está na versão mais recente ({self.atual})."
        base = f"Há uma versão nova do Optimus: {self.alvo.versao} (você usa {self.atual})."
        extra = {
            "versao_maior": " É uma versão maior, então só instalo com o seu sim.",
            "aguardando": " Ela é recente: espero o período de segurança antes de instalar "
                          "sozinho.",
            "fora_da_janela": " Instalo sozinho no próximo horário de atualização.",
            "disponivel": " Posso instalar agora." if not self.instalar_sozinho
                          else " Vou instalar agora.",
        }
        return base + extra.get(self.motivo, "")

    def para_dict(self) -> dict[str, Any]:
        return {"atual": self.atual, "disponivel": self.disponivel, "motivo": self.motivo,
                "versao_nova": str(self.alvo.versao) if self.alvo else "",
                "notas": self.alvo.notas[:2000] if self.alvo else "",
                "instalar_sozinho": self.instalar_sozinho,
                "pede_confirmacao": self.pede_confirmacao, "mensagem": self.mensagem()}


def dentro_da_janela(agora: datetime, janela: str) -> bool:
    """Diz se `agora` (hora local) está na janela "HH:MM-HH:MM". Aceita virar a meia-noite."""
    if not janela or "-" not in janela:
        return True
    try:
        ini_s, fim_s = (p.strip() for p in janela.split("-", 1))
        ini, fim = time.fromisoformat(ini_s), time.fromisoformat(fim_s)
    except ValueError:
        return True  # janela mal escrita não bloqueia; só a confirmação/espera valem
    t = agora.time().replace(tzinfo=None)
    if ini <= fim:
        return ini <= t < fim
    return t >= ini or t < fim  # ex.: 22:00-03:00


def decidir(atual: str, releases: list[Release], politica: Politica,
            agora: datetime | None = None) -> Decisao:
    """Escolhe a release alvo e se ela pode ser instalada sozinha. Sem rede, sem efeitos."""
    agora = agora or datetime.now(timezone.utc)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    v_atual = Versao.ler(atual)
    beta = politica.canal == "beta"
    candidatas = [r for r in releases
                  if not r.draft and (beta or (not r.prerelease and not r.versao.pre))
                  and r.versao > v_atual]
    if not candidatas:
        return Decisao(atual=str(v_atual), alvo=None, motivo="atualizado")
    alvo = max(candidatas, key=lambda r: r.versao._chave())
    if alvo.versao.maior > v_atual.maior:
        return Decisao(str(v_atual), alvo, "versao_maior", pede_confirmacao=True)
    if agora < alvo.publicada + timedelta(hours=politica.espera_horas):
        return Decisao(str(v_atual), alvo, "aguardando")
    if not dentro_da_janela(agora.astimezone(), politica.janela):
        return Decisao(str(v_atual), alvo, "fora_da_janela")
    return Decisao(str(v_atual), alvo, "disponivel", instalar_sozinho=politica.automatico)


# ---------------------------------------------------------------------- instalar / voltar
def _baixar_padrao(url: str) -> bytes:
    import httpx

    with httpx.Client(timeout=120, follow_redirects=True,
                      headers={"User-Agent": "open-optimus-updater"}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


def _somas(texto: str) -> dict[str, str]:
    saida = {}
    for linha in texto.splitlines():
        partes = linha.strip().split()
        if len(partes) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", partes[0]):
            saida[partes[-1].lstrip("*")] = partes[0].lower()
    return saida


def _pasta_backups() -> Path:
    from optimus.config import pasta_base

    return pasta_base() / "backups"


def _pacote_no_zip(arquivo: zipfile.ZipFile) -> str:
    """Prefixo dentro do ZIP onde fica `optimus/__init__.py` ("" ou "pasta-raiz/")."""
    for nome in arquivo.namelist():
        if nome.endswith("optimus/__init__.py"):
            return nome[: -len("optimus/__init__.py")]
    raise ErroRelease("O pacote baixado não contém o Optimus (optimus/__init__.py).")


def _extrair_pacote(conteudo: bytes, destino: Path) -> None:
    """Extrai só a pasta `optimus/` do ZIP para `destino`, sem sair dela (zip-slip)."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        prefixo = _pacote_no_zip(z) + "optimus/"
        raiz = destino.resolve()
        for info in z.infolist():
            if not info.filename.startswith(prefixo) or info.is_dir():
                continue
            relativo = info.filename[len(prefixo):]
            alvo = (raiz / relativo).resolve()
            if not alvo.is_relative_to(raiz):
                raise ErroRelease(f"Arquivo suspeito no pacote: {info.filename}")
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as origem, open(alvo, "wb") as saida:
                shutil.copyfileobj(origem, saida)


def instalar(release: Release, pasta_programa: Path, versao_atual: str,
             baixar: Callable[[str], bytes] | None = None, exigir_soma: bool = True) -> dict:
    """Baixa, confere e instala a release. Guarda a versão atual para poder voltar.

    `pasta_programa` é a pasta que contém o pacote `optimus/` (a pasta "site-packages" ou a
    raiz do projeto).
    """
    baixar = baixar or _baixar_padrao
    nome, url = release.pacote()
    if not url:
        if exigir_soma:
            raise ErroRelease("Esta release não tem o pacote optimus-*.zip com soma SHA-256. "
                              "Por segurança, não instalo.")
        nome, url = "", release.zip_url
    conteudo = baixar(url)
    if exigir_soma:
        url_somas = release.assets.get(NOME_SOMAS, "")
        if not url_somas:
            raise ErroRelease("A release não publicou SHA256SUMS. Por segurança, não instalo.")
        esperado = _somas(baixar(url_somas).decode("utf-8", "replace")).get(nome)
        obtido = hashlib.sha256(conteudo).hexdigest()
        if not esperado or esperado != obtido:
            raise ErroRelease("A soma SHA-256 do pacote não confere. O download pode estar "
                              "corrompido ou adulterado; nada foi alterado.")
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:  # confere antes de mexer em qualquer coisa
        _pacote_no_zip(z)
        if z.testzip() is not None:
            raise ErroRelease("O pacote baixado está corrompido; nada foi alterado.")

    pasta_programa = Path(pasta_programa)
    atual = pasta_programa / "optimus"
    backups = _pasta_backups()
    backups.mkdir(parents=True, exist_ok=True)
    copia = backups / f"optimus-{versao_atual}"
    if copia.exists():
        shutil.rmtree(copia)
    shutil.copytree(atual, copia, ignore=shutil.ignore_patterns("__pycache__"))

    with tempfile.TemporaryDirectory() as tmp:
        novo = Path(tmp) / "optimus"
        _extrair_pacote(conteudo, novo)
        try:
            shutil.rmtree(atual)
            shutil.copytree(novo, atual)
        except OSError as erro:  # restaura a cópia se a troca falhar no meio
            shutil.rmtree(atual, ignore_errors=True)
            shutil.copytree(copia, atual)
            raise ErroRelease(f"Falha ao trocar os arquivos; versão anterior restaurada: {erro}")

    (backups / "ultima.json").write_text(json.dumps(
        {"anterior": versao_atual, "nova": str(release.versao), "copia": str(copia),
         "pasta_programa": str(pasta_programa),
         "quando": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {"ok": True, "mudou": True, "versao": str(release.versao),
            "mensagem": f"Optimus atualizado para {release.versao}. Reinicie para usar a nova "
                        f"versão. Se algo der errado: optimus atualizar --voltar."}


def voltar() -> dict:
    """Desfaz a última atualização feita por release."""
    registro = _pasta_backups() / "ultima.json"
    if not registro.exists():
        return {"ok": False, "erro": "Não há atualização para desfazer."}
    dados = json.loads(registro.read_text(encoding="utf-8"))
    copia, destino = Path(dados["copia"]), Path(dados["pasta_programa"]) / "optimus"
    if not (copia / "__init__.py").exists():
        return {"ok": False, "erro": f"A cópia de segurança sumiu: {copia}"}
    shutil.rmtree(destino, ignore_errors=True)
    shutil.copytree(copia, destino)
    registro.unlink()
    return {"ok": True, "versao": dados["anterior"],
            "mensagem": f"Voltei para a versão {dados['anterior']}. Reinicie o Optimus."}
