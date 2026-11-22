"""Receitas e pastas observadas do estúdio.

- **Receita**: uma ação do estúdio com as opções já escolhidas, salva com um nome
  ("Dublar para inglês com a minha voz", "Legendar em pt-BR e gravar no vídeo"). Roda num
  arquivo com um clique, pelo chat ou pela linha de comando.
- **Pasta observada**: cada arquivo novo que aparece na pasta passa pela receita sozinho.
  Ex.: tudo que cair em "Vídeos/para dublar" sai dublado na pasta de saídas.

Ficam em `<pasta do Optimus>/estudio/receitas.json` e `observadas.json`.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from optimus.estudio import pasta_estudio
from optimus.estudio.audio import ErroEstudio

EXTENSOES = (".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".wav", ".m4a", ".ogg", ".flac",
             ".opus", ".aac", ".txt", ".md", ".epub", ".pdf", ".docx", ".srt", ".vtt")
ACOES_PERMITIDAS = {"estudio_legendar", "estudio_dublar", "estudio_transcrever",
                    "estudio_traduzir_legenda", "estudio_separar_voz", "estudio_quem_fala",
                    "estudio_verificar_ia", "estudio_audiolivro", "estudio_converter_voz"}


@dataclass
class Receita:
    nome: str
    acao: str  # nome da ferramenta (estudio_dublar...)
    opcoes: dict = field(default_factory=dict)
    descricao: str = ""
    pronta: bool = False

    def para_dict(self) -> dict:
        return asdict(self)


PRONTAS = [
    Receita("Legendar em português", "estudio_legendar", {"idioma": "pt-BR"},
            "Transcreve e cria a legenda SRT em português do Brasil", True),
    Receita("Legendar e gravar no vídeo", "estudio_legendar",
            {"idioma": "pt-BR", "no_video": "queimada"},
            "Legenda em pt-BR já desenhada no vídeo", True),
    Receita("Dublar para português", "estudio_dublar", {"idioma": "pt-BR"},
            "Dublagem para pt-BR com a voz padrão", True),
    Receita("Dublar para inglês", "estudio_dublar", {"idioma": "en-US"},
            "Dublagem para inglês com a voz padrão", True),
    Receita("Transcrever", "estudio_transcrever", {"formato": "srt"},
            "Texto com tempo (SRT)", True),
    Receita("Separar voz e música", "estudio_separar_voz", {},
            "Tira a música e os efeitos, deixa só a voz", True),
    Receita("Virar audiolivro", "estudio_audiolivro", {},
            "Livro ou texto narrado, com capítulos (M4B)", True),
]


def _arq(nome: str) -> Path:
    return pasta_estudio() / nome


def _ler(nome: str) -> list[dict]:
    try:
        dados = json.loads(_arq(nome).read_text(encoding="utf-8"))
        return dados if isinstance(dados, list) else []
    except (OSError, ValueError):
        return []


def _gravar(nome: str, dados: list[dict]) -> None:
    _arq(nome).parent.mkdir(parents=True, exist_ok=True)
    _arq(nome).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------- receitas
def receitas() -> list[Receita]:
    proprias = []
    for d in _ler("receitas.json"):
        try:
            proprias.append(Receita(**{k: v for k, v in d.items()
                                       if k in Receita.__dataclass_fields__}))
        except TypeError:
            continue
    nomes = {r.nome.lower() for r in proprias}
    return proprias + [r for r in PRONTAS if r.nome.lower() not in nomes]


def receita(nome: str) -> Receita:
    alvo = (nome or "").strip().lower()
    todas = receitas()
    for r in todas:
        if r.nome.lower() == alvo:
            return r
    for r in todas:
        if alvo and alvo in r.nome.lower():
            return r
    raise ErroEstudio(f"Não achei a receita '{nome}'. Receitas: "
                      + ", ".join(r.nome for r in todas))


def salvar_receita(nome: str, acao: str, opcoes: dict | None = None,
                   descricao: str = "") -> Receita:
    acao = acao if acao.startswith("estudio_") else "estudio_" + acao
    if acao not in ACOES_PERMITIDAS:
        raise ErroEstudio("Ações possíveis numa receita: " + ", ".join(sorted(ACOES_PERMITIDAS)))
    if not nome.strip():
        raise ErroEstudio("Dê um nome para a receita.")
    opcoes = {k: v for k, v in (opcoes or {}).items() if k != "arquivo"}
    nova = Receita(nome.strip(), acao, opcoes, descricao.strip())
    dados = [d for d in _ler("receitas.json") if str(d.get("nome", "")).lower()
             != nova.nome.lower()]
    _gravar("receitas.json", dados + [nova.para_dict()])
    return nova


def apagar_receita(nome: str) -> bool:
    dados = _ler("receitas.json")
    restantes = [d for d in dados if str(d.get("nome", "")).lower() != nome.strip().lower()]
    _gravar("receitas.json", restantes)
    return len(restantes) != len(dados)


def aplicar(nome_receita: str, arquivo: str | Path, config=None) -> dict:
    """Roda a receita num arquivo (as ações longas vão para a fila do estúdio)."""
    from optimus.tools.base import Contexto, registradas

    r = receita(nome_receita)
    if r.acao not in ACOES_PERMITIDAS:
        raise ErroEstudio(f"A receita '{r.nome}' usa uma ação que não pode rodar sozinha.")
    ferramenta = registradas().get(r.acao)
    if ferramenta is None:
        import optimus.tools.estudio  # noqa: F401 - registra as ferramentas

        ferramenta = registradas()[r.acao]
    argumentos = {k: v for k, v in r.opcoes.items() if k in ferramenta.parametros}
    argumentos["arquivo"] = str(Path(arquivo).resolve())
    ctx = Contexto(config=config, pasta_trabalho=Path(arquivo).resolve().parent)
    resultado = ferramenta.funcao(ctx, **argumentos)
    return resultado if isinstance(resultado, dict) else {"resultado": resultado}


# ---------------------------------------------------------------------- pastas observadas
def observadas() -> list[dict]:
    return _ler("observadas.json")


def observar(pasta: str | Path, nome_receita: str) -> dict:
    alvo = Path(pasta).expanduser().resolve()
    if not alvo.is_dir():
        raise ErroEstudio(f"Pasta não encontrada: {alvo}")
    r = receita(nome_receita)
    dados = [d for d in observadas() if d.get("pasta") != str(alvo)]
    novo = {"pasta": str(alvo), "receita": r.nome, "desde": time.time()}
    _gravar("observadas.json", dados + [novo])
    # Arquivos que já estavam na pasta não são processados: só os que chegarem depois
    _gravar_vistos({**_vistos(), **{_chave(f): time.time() for f in _arquivos(alvo)}})
    return novo


def parar_de_observar(pasta: str | Path) -> bool:
    alvo = str(Path(pasta).expanduser().resolve())
    dados = observadas()
    restantes = [d for d in dados if d.get("pasta") != alvo]
    _gravar("observadas.json", restantes)
    return len(restantes) != len(dados)


def _arquivos(pasta: Path) -> list[Path]:
    try:
        return sorted(f for f in pasta.iterdir() if f.is_file()
                      and f.suffix.lower() in EXTENSOES and not f.name.startswith((".", "~")))
    except OSError:
        return []


def _chave(f: Path) -> str:
    try:
        st = f.stat()
        return f"{f.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        return str(f)


def _vistos() -> dict:
    try:
        return json.loads(_arq("observadas-vistos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_vistos(vistos: dict) -> None:
    if len(vistos) > 5000:  # guarda só os mais recentes
        vistos = dict(sorted(vistos.items(), key=lambda kv: kv[1])[-5000:])
    _arq("observadas-vistos.json").parent.mkdir(parents=True, exist_ok=True)
    _arq("observadas-vistos.json").write_text(json.dumps(vistos), encoding="utf-8")


class Observador:
    """Olha as pastas de tempos em tempos. Um arquivo só é processado quando parou de crescer
    (terminou de copiar)."""

    def __init__(self, config=None, intervalo: float = 10.0, ao_processar=None):
        self.config = config
        self.intervalo = intervalo
        self.ao_processar = ao_processar
        self._tamanhos: dict[str, int] = {}
        self._parar = threading.Event()
        self._linha: threading.Thread | None = None

    def uma_vez(self) -> list[dict]:
        feitos = []
        vistos = _vistos()
        for regra in observadas():
            for f in _arquivos(Path(regra.get("pasta", ""))):
                chave = _chave(f)
                if chave in vistos:
                    continue
                tamanho = f.stat().st_size
                if self._tamanhos.get(str(f)) != tamanho:  # ainda copiando: espera a próxima
                    self._tamanhos[str(f)] = tamanho
                    continue
                vistos[chave] = time.time()
                _gravar_vistos(vistos)
                try:
                    resultado = aplicar(regra["receita"], f, self.config)
                except Exception as erro:  # noqa: BLE001 - um arquivo ruim não para a pasta
                    resultado = {"erro": str(erro)}
                item = {"arquivo": str(f), "receita": regra["receita"], "resultado": resultado}
                feitos.append(item)
                if self.ao_processar:
                    self.ao_processar(item)
        return feitos

    def _rodar(self) -> None:
        while not self._parar.wait(self.intervalo):
            try:
                self.uma_vez()
            except Exception:  # noqa: BLE001
                pass

    def iniciar(self) -> Observador:
        if not self._linha or not self._linha.is_alive():
            self._parar.clear()
            self._linha = threading.Thread(target=self._rodar, daemon=True,
                                           name="estudio-observador")
            self._linha.start()
        return self

    def parar(self) -> None:
        self._parar.set()


_OBSERVADOR: Observador | None = None


def iniciar_se_preciso(config=None) -> Observador | None:
    """Liga o observador em segundo plano se houver alguma pasta configurada."""
    global _OBSERVADOR
    if not observadas():
        return None
    if _OBSERVADOR is None:
        _OBSERVADOR = Observador(config)
    return _OBSERVADOR.iniciar()
