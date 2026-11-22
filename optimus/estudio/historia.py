"""Histórias, podcasts e diálogos com várias vozes, a partir de um roteiro simples.

Formato do roteiro (uma fala por linha; linhas sem nome ficam com o Narrador):

    Narrador: Era uma noite fria em São Paulo.
    Ana: Você ouviu isso?
    [Bruno] Foi só o vento.
    (pausa 2)

Cada personagem recebe uma voz (a que você escolher em `elenco`, ou uma diferente para cada
um). Sai um único arquivo de áudio e uma legenda SRT com o nome de quem fala.
"""

from __future__ import annotations

import re
from pathlib import Path

from optimus.estudio import audio, legendas, motores, pasta_saidas, registrar, vozes
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho

TAXA = motores.TAXA
NARRADOR = "Narrador"
VOZES_PERSONAGENS = ["prime", "valkyrie", "nexus", "aurora", "titan", "lyra", "mordomo"]
_COLCHETE = re.compile(r"^\s*\[([^\]]{1,40})\]\s*:?\s*(.+)$")
_DOIS_PONTOS = re.compile(r"^\s*([^\s:\[(][^:]{0,39}?)\s*:\s+(.+)$")
_PAUSA = re.compile(r"^\s*[(\[]\s*pausa\s*(\d+(?:[.,]\d+)?)?\s*s?\s*[)\]]\s*$", re.IGNORECASE)


def _silencio(segundos: float):
    import numpy as np

    return np.zeros(int(max(0.0, segundos) * TAXA), dtype=np.float32)


def ler_roteiro(texto: str) -> list[tuple[str, str]]:
    """[(personagem, fala)]. Uma pausa vira ("", "2.0")."""
    falas: list[tuple[str, str]] = []
    for linha in texto.splitlines():
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        pausa = _PAUSA.match(linha)
        if pausa:
            falas.append(("", (pausa.group(1) or "1").replace(",", ".")))
            continue
        achado = _COLCHETE.match(linha) or _DOIS_PONTOS.match(linha)
        quem = achado.group(1).strip() if achado else ""
        if quem and len(quem.split()) <= 4 and not quem.lower().startswith(("http", "obs")):
            falas.append((quem, achado.group(2).strip()))
        else:
            falas.append((NARRADOR, linha.strip()))
    return falas


def personagens(falas: list[tuple[str, str]]) -> list[str]:
    vistos: list[str] = []
    for quem, _ in falas:
        if quem and quem not in vistos:
            vistos.append(quem)
    return vistos


def montar_elenco(nomes: list[str], elenco: dict[str, str] | None = None,
                  narrador: str = "") -> dict[str, vozes.Perfil]:
    """Escolhe a voz de cada personagem: a pedida, senão uma diferente para cada um."""
    pedidos = {k.strip().lower(): v for k, v in (elenco or {}).items()}
    saida: dict[str, vozes.Perfil] = {}
    usadas: set[str] = set()
    for quem in nomes:
        escolha = pedidos.get(quem.lower()) or (narrador if quem == NARRADOR else "")
        if escolha:
            saida[quem] = vozes.obter(escolha)
            usadas.add(saida[quem].id)
    livres = [v for v in VOZES_PERSONAGENS if v not in usadas]
    for n, quem in enumerate(q for q in nomes if q not in saida):
        saida[quem] = vozes.obter(livres[n % len(livres)] if livres
                                  else VOZES_PERSONAGENS[n % len(VOZES_PERSONAGENS)])
    return saida


def gerar(roteiro: str, elenco: dict[str, str] | None = None, narrador: str = "",
          idioma: str = "", titulo: str = "", formato: str = "mp3", pausa: float = 0.45,
          velocidade: float = 1.0, config=None, progresso=None, cancelado=None,
          saida: str | Path | None = None) -> dict:
    """Gera a história inteira. `roteiro` pode ser o texto ou o caminho de um .txt."""
    caminho = Path(roteiro) if len(roteiro) < 400 and "\n" not in roteiro else None
    if caminho and caminho.suffix.lower() in (".txt", ".md") and caminho.exists():
        titulo = titulo or caminho.stem
        roteiro = caminho.read_text(encoding="utf-8-sig", errors="replace")
    falas = ler_roteiro(roteiro)
    if not any(quem for quem, _ in falas):
        raise ErroEstudio("O roteiro está vazio.")
    nomes = personagens(falas)
    perfis = montar_elenco(nomes, elenco, narrador)
    partes, trechos, t = [], [], 0.0
    silencio = _silencio(pausa)
    for n, (quem, fala) in enumerate(falas):
        if cancelado and cancelado():
            raise ErroEstudio("Cancelado.")
        if progresso:
            progresso(n / len(falas), f"Fala {n + 1} de {len(falas)} ({quem or 'pausa'})")
        if not quem:
            pedaco = _silencio(float(fala))
            partes.append(pedaco)
            t += len(pedaco) / TAXA
            continue
        x = audio.cortar_silencio(motores.gerar(fala, perfis[quem], idioma, velocidade, config,
                                                cancelado=cancelado), TAXA)
        trechos.append(Trecho(round(t, 3), round(t + len(x) / TAXA, 3), fala, quem))
        partes += [x, silencio]
        t += (len(x) + len(silencio)) / TAXA
    import numpy as np

    tudo = np.concatenate(partes) if partes else np.zeros(1, dtype=np.float32)
    titulo = titulo or "historia"
    nome = re.sub(r"[^\w -]+", "", titulo)[:60].strip() or "historia"
    pasta = Path(saida) if saida else pasta_saidas(config)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = audio.salvar(audio.normalizar(tudo), TAXA,
                           pasta / f"{nome}.{formato.lstrip('.') or 'mp3'}", titulo=titulo)
    srt = legendas.salvar(trechos, pasta / f"{nome}.srt", com_falante=True)
    registrar("historia", arquivo, roteiro[:300], ", ".join(p.nome for p in perfis.values()),
              idioma)
    return {"arquivo": str(arquivo), "legenda": str(srt), "falas": len(trechos),
            "duracao": round(len(tudo) / TAXA, 1),
            "elenco": {quem: p.nome for quem, p in perfis.items()}}
