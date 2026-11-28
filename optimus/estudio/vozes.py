"""Perfis de voz do estúdio: vozes prontas, clonadas (com consentimento) e criadas por descrição.

Cada perfil salvo fica em `estudio/vozes/<id>/` com `perfil.json` e, se for clonada,
`amostra.wav`. Um perfil pode ser exportado num arquivo `.optimusvoz` (zip) e importado em
outro PC.

Clonar exige declarar que a voz é sua ou que você tem autorização da pessoa. A declaração fica
gravada no perfil, e todo áudio gerado leva a etiqueta "gerado por IA".
"""

from __future__ import annotations

import json
import re
import shutil
import time
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from optimus.config import pasta_base
from optimus.estudio import audio
from optimus.estudio.audio import ErroEstudio

TAXA_AMOSTRA = 24000
MIN_AMOSTRA, MAX_AMOSTRA = 5.0, 90.0
DECLARACAO = ("Declaro que esta voz é minha ou que tenho autorização da pessoa para cloná-la, "
              "e que não vou usá-la para enganar ninguém.")


@dataclass
class Perfil:
    id: str
    nome: str
    tipo: str = "pronta"  # pronta | clonada | criada
    motor: str = "padrao"  # padrao (vozes do Optimus) | edge | clone | omnivoice | piper | remoto
    base: str = ""  # voz do Optimus (prime, valkyrie...) ou voz do motor
    genero: str = "feminina"
    idioma: str = "pt-BR"
    velocidade: float = 1.0
    tom: float = 0.0  # semitons (-6 grave ... +6 aguda)
    efeito: str = ""  # "" | cyber | sussurro
    expressividade: float = 0.5  # 0 neutra ... 1 dramática (vozes clonadas)
    descricao: str = ""
    instrucao: str = ""  # atributos para o OmniVoice ("female, elderly, low pitch")
    amostra: str = ""  # nome do arquivo dentro da pasta do perfil
    consentimento: dict = field(default_factory=dict)
    criado: float = 0.0
    favorito: bool = False

    def caminho_amostra(self) -> Path | None:
        if not self.amostra:
            return None
        return pasta_vozes() / self.id / self.amostra

    def para_dict(self) -> dict:
        d = asdict(self)
        d.pop("consentimento", None)
        d["clonada"] = self.tipo == "clonada"
        return d


def pasta_vozes() -> Path:
    return pasta_base() / "estudio" / "vozes"


def _normal(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def _slug(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normal(nome)).strip("-")[:40] or "voz"


# ---------------------------------------------------------------------- vozes prontas
def _prontas() -> list[Perfil]:
    from optimus.voice import tts
    # Importar antes de consultar o estado do motor; o módulo também é usado
    # para montar a instrução de voz quando os pesos já estão preparados.
    from optimus.estudio import omnivoice, piper

    # O perfil Edton Braz do Estúdio é uma configuração própria (OmniVoice
    # quando disponível, Prime como reserva). Não deixar a voz ElevenLabs
    # homônima de tts.VOZES sombreá-lo na busca por id/nome.
    saida = [Perfil(v.id, v.nome, "pronta", "padrao", v.id, v.genero, "pt-BR",
                    descricao=v.descricao) for v in tts.VOZES if v.id != "edton-braz"]
    # Perfil de narração PT-BR do proprietário. Quando os pesos do OmniVoice estão
    # preparados localmente, usa voice design; caso contrário, cai para a voz Prime.
    pesos_omnivoice = pasta_base() / "estudio" / "modelos" / ".prontos" / "omnivoice.ok"
    motor_edton = "omnivoice" if omnivoice.instalado() and pesos_omnivoice.is_file() else "padrao"
    descricao_edton = ("Narrador jovem-adulto de ciência e tecnologia; PT-BR urbano neutro, "
                       "dicção nítida e coloquial, timbre médio/médio-agudo claro, projeção "
                       "próxima e seca, ritmo ágil sem atropelar, micro-pausas estratégicas, "
                       "perguntas curiosas, ênfase controlada em números e contrastes, "
                       "fechamentos firmes e amigáveis. Com a chave da ElevenLabs em "
                       "Configurações, usa a voz original (Matheus) pela API.")
    instrucao_edton = omnivoice.instrucao(
        "narrador masculino jovem brasileiro, voz clara e brilhante, timbre médio-agudo, "
        "estilo educativo de ciência e tecnologia, conversacional e confiante, ritmo ágil, "
        "dicção precisa e entonação expressiva", "masculina"
    ) if motor_edton == "omnivoice" else ""
    saida.append(Perfil(
        "edton-braz", "Edton Braz", "pronta", motor_edton,
        "" if motor_edton == "omnivoice" else "prime", "masculina", "pt-BR",
        velocidade=1.08, tom=0.5, expressividade=0.75,
        descricao=descricao_edton, instrucao=instrucao_edton))
    # Voz original do Optimus: um mordomo calmo e formal (não imita nenhuma voz existente).
    saida.append(Perfil("mordomo", "Mordomo", "pronta", "padrao", "nexus", "masculina",
                        velocidade=0.92, tom=-1.5,
                        descricao="Original do Optimus: mordomo calmo, formal e grave"))
    if piper.instalado():
        saida += [Perfil(v.perfil_id, v.nome, "pronta", "piper", v.id, v.genero, v.idioma,
                         descricao=f"Offline e leve (Piper, {v.licenca}); baixa "
                                   f"~{v.tamanho_mb} MB na primeira vez") for v in piper.VOZES]
    if omnivoice.instalado():
        saida.append(Perfil("omnivoice-auto", "Automática (OmniVoice)", "pronta", "omnivoice",
                            "", "feminina", "pt-BR",
                            descricao="O OmniVoice escolhe uma voz natural para o idioma"))
    saida.append(Perfil("remota", "Servidor remoto", "pronta", "remoto", "", "feminina",
                        descricao="Voz do servidor configurado em estudio.servidor_voz_url"))
    return saida


# ---------------------------------------------------------------------- salvar e ler
def _salvar(p: Perfil) -> Perfil:
    pasta = pasta_vozes() / p.id
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "perfil.json").write_text(json.dumps(asdict(p), ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return p


def _ler(pasta: Path) -> Perfil | None:
    try:
        dados = json.loads((pasta / "perfil.json").read_text(encoding="utf-8"))
        campos = Perfil.__dataclass_fields__
        return Perfil(**{k: v for k, v in dados.items() if k in campos})
    except (OSError, ValueError, TypeError):
        return None


def salvas() -> list[Perfil]:
    if not pasta_vozes().exists():
        return []
    return [p for p in (_ler(d) for d in sorted(pasta_vozes().iterdir()) if d.is_dir()) if p]


def listar() -> list[Perfil]:
    proprias = salvas()
    ids = {p.id for p in proprias}
    return proprias + [p for p in _prontas() if p.id not in ids]


def obter(nome: str) -> Perfil:
    """Acha por id ou nome ("Nexus", "minha voz"). Sem nome: a voz padrão (Valkyrie)."""
    if not nome:
        nome = "valkyrie"
    alvo = _normal(nome)
    todas = listar()
    for p in todas:
        if alvo in (_normal(p.id), _normal(p.nome)):
            return p
    from optimus.voice import tts

    pronta = tts.buscar_voz(nome)
    if pronta:
        return next(p for p in todas if p.id == pronta.id)
    for p in todas:
        if alvo and alvo in _normal(p.nome):
            return p
    raise ErroEstudio(f"Não achei a voz '{nome}'. Vozes: " + ", ".join(p.nome for p in todas))


def _novo_id(nome: str) -> str:
    base, n = _slug(nome), 1
    # IDs de vozes prontas podem ser sobrescritos por um perfil pessoal
    # (ex.: a voz pública "Edton Braz" será substituída pela amostra do proprietário).
    existentes = {p.id for p in salvas()}
    novo = base
    while novo in existentes:
        n += 1
        novo = f"{base}-{n}"
    return novo


# ---------------------------------------------------------------------- clonar
def preparar_amostra(origem: str | Path, destino: Path, inicio: float = 0.0,
                     fim: float = 0.0):
    """Lê qualquer áudio/vídeo, recorta, tira silêncio das pontas e normaliza (24 kHz mono)."""
    x = audio.carregar(origem, TAXA_AMOSTRA)
    if fim and fim > inicio:
        x = x[int(inicio * TAXA_AMOSTRA): int(fim * TAXA_AMOSTRA)]
    elif inicio:
        x = x[int(inicio * TAXA_AMOSTRA):]
    x = audio.normalizar(audio.cortar_silencio(x, TAXA_AMOSTRA))
    segundos = len(x) / TAXA_AMOSTRA
    if segundos < MIN_AMOSTRA:
        raise ErroEstudio(f"A amostra tem só {segundos:.1f} s de fala. Grave pelo menos "
                          f"{MIN_AMOSTRA:.0f} s (o ideal é de 10 a 30 s, sem música).")
    if segundos > MAX_AMOSTRA:
        x = x[: int(MAX_AMOSTRA * TAXA_AMOSTRA)]
        segundos = MAX_AMOSTRA
    audio.salvar(x, TAXA_AMOSTRA, destino, marca_ia=False)
    return segundos


def clonar(nome: str, amostra: str | Path, consentimento: bool, idioma: str = "pt-BR",
           genero: str = "", descricao: str = "", inicio: float = 0.0, fim: float = 0.0,
           expressividade: float = 0.5) -> Perfil:
    if not consentimento:
        raise ErroEstudio("Para clonar, confirme que a voz é sua ou que você tem autorização "
                          "da pessoa (consentimento=true).")
    p = Perfil(_novo_id(nome), nome.strip() or "Minha voz", "clonada", "clone", "",
               genero or "feminina", idioma, descricao=descricao, amostra="amostra.wav",
               expressividade=max(0.0, min(1.0, float(expressividade))),
               consentimento={"declaracao": DECLARACAO, "quando": time.strftime("%Y-%m-%d %H:%M"),
                              "origem": Path(str(amostra)).name},
               criado=time.time())
    pasta = pasta_vozes() / p.id
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        segundos = preparar_amostra(amostra, pasta / "amostra.wav", inicio, fim)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    p.descricao = p.descricao or f"Clonada de {p.consentimento['origem']} ({segundos:.0f} s)"
    return _salvar(p)


# ---------------------------------------------------------------------- criar por descrição
_DESCRITORES: list[tuple[tuple[str, ...], dict]] = [
    (("feminina", "mulher", "moca", "senhora", "garota"), {"genero": "feminina"}),
    (("masculina", "homem", "rapaz", "senhor", "garoto"), {"genero": "masculina"}),
    (("grave", "rouca", "profunda", "encorpada", "trovao"), {"tom": -3.0}),
    (("aguda", "fina", "leve"), {"tom": 2.5}),
    (("crianca", "infantil"), {"tom": 5.0, "velocidade": 1.05}),
    (("idosa", "idoso", "velha", "velho", "anciao", "avo"), {"tom": -1.5, "velocidade": 0.88}),
    (("jovem", "adolescente"), {"tom": 1.0, "velocidade": 1.05}),
    (("calma", "calmo", "tranquila", "tranquilo", "serena", "suave", "relaxante", "lenta"),
     {"velocidade": 0.9, "expressividade": 0.3}),
    (("rapida", "rapido", "animada", "animado", "energica", "empolgada", "locutor", "vendedor"),
     {"velocidade": 1.1, "expressividade": 0.7}),
    (("dramatica", "dramatico", "epica", "epico", "trailer", "teatral", "expressiva"),
     {"expressividade": 0.85, "velocidade": 0.95}),
    (("neutra", "neutro", "jornal", "noticia", "corporativa", "formal", "seria"),
     {"expressividade": 0.3}),
    (("sussurro", "sussurrando", "asmr", "noturna", "baixinho"), {"efeito": "sussurro"}),
    (("robo", "robotica", "robotico", "maquina", "android", "sintetica", "futurista"),
     {"efeito": "cyber"}),
]


def interpretar_descricao(descricao: str) -> dict:
    """Transforma "voz masculina grave e calma" em parâmetros. Sem palavras conhecidas,
    devolve só o padrão (voz feminina natural)."""
    t = _normal(descricao)
    palavras = set(re.findall(r"[a-z]+", t))
    ajustes: dict = {"genero": "feminina", "tom": 0.0, "velocidade": 1.0,
                     "expressividade": 0.5, "efeito": ""}
    vistos: list[str] = []
    for chaves, valores in _DESCRITORES:
        if palavras & set(chaves):
            for k, v in valores.items():
                if k in ("tom",) and ajustes[k]:
                    ajustes[k] += v  # "grave e idosa" soma
                else:
                    ajustes[k] = v
            vistos.append(chaves[0])
    ajustes["tom"] = max(-6.0, min(6.0, ajustes["tom"]))
    ajustes["entendido"] = vistos
    return ajustes


def criar(nome: str, descricao: str, idioma: str = "pt-BR", base: str = "",
          motor: str = "") -> Perfil:
    """Cria uma voz nova a partir de uma descrição ("voz feminina jovem e animada").

    Com o OmniVoice instalado (ou `motor="omnivoice"`), a voz é desenhada pelo próprio modelo
    a partir da descrição. Sem ele, usa uma voz pronta como ponto de partida e ajusta tom,
    ritmo, expressão e efeito. Se a base for uma voz clonada, os ajustes valem sobre ela."""
    from optimus.estudio import omnivoice

    ajustes = interpretar_descricao(descricao)
    if motor == "omnivoice" or (not motor and not base and omnivoice.instalado()):
        p = Perfil(_novo_id(nome), nome.strip() or "Voz criada", "criada", "omnivoice", "",
                   ajustes["genero"], idioma, velocidade=ajustes["velocidade"],
                   efeito="cyber" if ajustes["efeito"] == "cyber" else "",
                   expressividade=ajustes["expressividade"], descricao=descricao.strip(),
                   instrucao=omnivoice.instrucao(descricao, ajustes["genero"]),
                   criado=time.time())
        return _salvar(p)
    origem = obter(base) if base else \
        obter("prime" if ajustes["genero"] == "masculina" else "valkyrie")
    p = Perfil(_novo_id(nome), nome.strip() or "Voz criada", "criada", origem.motor,
               origem.base or origem.id, ajustes["genero"], idioma,
               velocidade=ajustes["velocidade"], tom=ajustes["tom"], efeito=ajustes["efeito"],
               expressividade=ajustes["expressividade"], descricao=descricao.strip(),
               criado=time.time())
    if origem.tipo == "clonada" and origem.caminho_amostra():
        p.motor, p.amostra, p.consentimento = "clone", "amostra.wav", origem.consentimento
        pasta = pasta_vozes() / p.id
        pasta.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem.caminho_amostra(), pasta / "amostra.wav")
    return _salvar(p)


# ---------------------------------------------------------------------- outras ações
def editar(nome: str, **campos) -> Perfil:
    p = obter(nome)
    if p.tipo == "pronta":  # ajustar uma pronta cria uma cópia salva
        p = Perfil(**{**asdict(p), "id": _novo_id(p.nome + " ajustada"),
                      "nome": p.nome + " (ajustada)", "tipo": "criada", "criado": time.time()})
    permitidos = {"nome", "velocidade", "tom", "efeito", "expressividade", "descricao",
                  "favorito", "genero", "idioma"}
    for k, v in campos.items():
        if k in permitidos and v is not None:
            setattr(p, k, v)
    return _salvar(p)


def apagar(nome: str) -> Perfil:
    p = obter(nome)
    if p.tipo == "pronta":
        raise ErroEstudio("As vozes prontas não podem ser apagadas.")
    shutil.rmtree(pasta_vozes() / p.id, ignore_errors=True)
    return p


def exportar(nome: str, destino: str | Path) -> Path:
    p = obter(nome)
    if p.tipo == "pronta":
        raise ErroEstudio("Vozes prontas já vêm com o Optimus; não precisam ser exportadas.")
    destino = Path(destino)
    if destino.suffix != ".optimusvoz":
        destino = destino.with_suffix(".optimusvoz")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("perfil.json", json.dumps(asdict(p), ensure_ascii=False, indent=1))
        if p.caminho_amostra() and p.caminho_amostra().exists():
            z.write(p.caminho_amostra(), "amostra.wav")
    return destino


def importar(arquivo: str | Path) -> Perfil:
    with zipfile.ZipFile(arquivo) as z:
        nomes = set(z.namelist())
        if "perfil.json" not in nomes or nomes - {"perfil.json", "amostra.wav"}:
            raise ErroEstudio("Arquivo .optimusvoz inválido.")
        dados = json.loads(z.read("perfil.json"))
        campos = Perfil.__dataclass_fields__
        p = Perfil(**{k: v for k, v in dados.items() if k in campos})
        if p.tipo == "clonada" and not p.consentimento:
            raise ErroEstudio("Voz clonada sem a declaração de consentimento: não importo.")
        p.id = _novo_id(p.nome)
        pasta = pasta_vozes() / p.id
        pasta.mkdir(parents=True, exist_ok=True)
        if "amostra.wav" in nomes:
            (pasta / "amostra.wav").write_bytes(z.read("amostra.wav"))
            p.amostra = "amostra.wav"
    return _salvar(p)
