"""Legendas: trechos com tempo, leitura e escrita de SRT, VTT e TXT, e quebra de linhas."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Trecho:
    inicio: float  # segundos
    fim: float
    texto: str
    falante: str = ""

    @property
    def duracao(self) -> float:
        return max(0.0, self.fim - self.inicio)

    def para_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------- tempo
def _tempo(segundos: float, separador: str) -> str:
    ms = int(round(max(0.0, segundos) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{separador}{ms:03d}"


def ler_tempo(texto: str) -> float:
    partes = texto.strip().replace(",", ".").split(":")
    if len(partes) == 2:
        partes.insert(0, "0")
    h, m, s = partes
    return int(h) * 3600 + int(m) * 60 + float(s)


_LINHA_TEMPO = re.compile(
    r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}")


# ---------------------------------------------------------------------- leitura
def ler(texto: str) -> list[Trecho]:
    """Lê SRT ou VTT (detecta sozinho). Tags como <i> e {\\an8} são removidas."""
    trechos: list[Trecho] = []
    blocos = re.split(r"\n\s*\n", texto.replace("\r\n", "\n").replace("\ufeff", "").strip())
    for bloco in blocos:
        linhas = [x for x in bloco.split("\n") if x.strip()]
        for i, linha in enumerate(linhas):
            if _LINHA_TEMPO.search(linha):
                ini, fim = [p.strip().split(" ")[0] for p in linha.split("-->")]
                corpo = "\n".join(linhas[i + 1:])
                corpo = re.sub(r"<[^>]+>|\{\\[^}]+\}", "", corpo).strip()
                falante = ""
                achado = re.match(r"^\[?([^\]:\n]{1,30})\]?:\s+", corpo)
                if achado and achado.group(1).strip().istitle():
                    falante, corpo = achado.group(1).strip(), corpo[achado.end():]
                if corpo:
                    trechos.append(Trecho(ler_tempo(ini), ler_tempo(fim), corpo, falante))
                break
    return trechos


def ler_arquivo(caminho: str | Path) -> list[Trecho]:
    return ler(Path(caminho).read_text(encoding="utf-8-sig", errors="replace"))


# ---------------------------------------------------------------------- escrita
def para_srt(trechos: list[Trecho], com_falante: bool = False) -> str:
    saida = []
    for n, t in enumerate(trechos, 1):
        corpo = f"{t.falante}: {t.texto}" if com_falante and t.falante else t.texto
        saida.append(f"{n}\n{_tempo(t.inicio, ',')} --> {_tempo(t.fim, ',')}\n{corpo}\n")
    return "\n".join(saida)


def para_vtt(trechos: list[Trecho], com_falante: bool = False) -> str:
    saida = ["WEBVTT", ""]
    for t in trechos:
        corpo = f"<v {t.falante}>{t.texto}" if com_falante and t.falante else t.texto
        saida += [f"{_tempo(t.inicio, '.')} --> {_tempo(t.fim, '.')}", corpo, ""]
    return "\n".join(saida)


def para_txt(trechos: list[Trecho], com_tempo: bool = False) -> str:
    linhas = []
    for t in trechos:
        prefixo = f"[{_tempo(t.inicio, '.')[:8]}] " if com_tempo else ""
        quem = f"{t.falante}: " if t.falante else ""
        linhas.append(f"{prefixo}{quem}{t.texto}")
    return "\n".join(linhas) + "\n"


def salvar(trechos: list[Trecho], caminho: str | Path, com_falante: bool = False) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    ext = caminho.suffix.lower()
    conteudo = (para_vtt(trechos, com_falante) if ext == ".vtt"
                else para_txt(trechos) if ext == ".txt"
                else para_srt(trechos, com_falante))
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


# ---------------------------------------------------------------------- ajustes
def quebrar_linhas(texto: str, largura: int = 42, max_linhas: int = 2) -> str:
    """Quebra em até `max_linhas` linhas equilibradas (padrão de legenda: 42 caracteres)."""
    palavras = texto.split()
    if len(texto) <= largura or not palavras:
        return texto
    if max_linhas == 2 and len(texto) <= largura * 2:
        melhor, diferenca = texto, len(texto)
        for i in range(1, len(palavras)):
            a, b = " ".join(palavras[:i]), " ".join(palavras[i:])
            if len(a) <= largura and len(b) <= largura and abs(len(a) - len(b)) < diferenca:
                melhor, diferenca = f"{a}\n{b}", abs(len(a) - len(b))
        return melhor
    linhas, atual = [], ""
    for p in palavras:
        if atual and len(atual) + 1 + len(p) > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    linhas.append(atual)
    return "\n".join(linhas)


def dividir_longos(trechos: list[Trecho], max_caracteres: int = 84,
                   max_segundos: float = 7.0) -> list[Trecho]:
    """Divide trechos longos demais para ler, repartindo o tempo pelo tamanho do texto."""
    saida: list[Trecho] = []
    for t in trechos:
        if len(t.texto) <= max_caracteres and t.duracao <= max_segundos:
            saida.append(t)
            continue
        frases = [f for f in re.split(r"(?<=[.!?;,])\s+", t.texto) if f.strip()]
        pedacos, atual = [], ""
        for f in frases:
            if atual and len(atual) + 1 + len(f) > max_caracteres:
                pedacos.append(atual)
                atual = f
            else:
                atual = f"{atual} {f}".strip()
        if atual:
            pedacos.append(atual)
        if len(pedacos) == 1 and len(pedacos[0]) > max_caracteres:  # sem pontuação
            palavras = pedacos[0].split()
            meio = len(palavras) // 2 or 1
            pedacos = [" ".join(palavras[:meio]), " ".join(palavras[meio:])]
        total = sum(len(p) for p in pedacos) or 1
        inicio = t.inicio
        for p in pedacos:
            fim = inicio + t.duracao * len(p) / total
            saida.append(Trecho(round(inicio, 3), round(fim, 3), p, t.falante))
            inicio = fim
    return saida


def deslocar(trechos: list[Trecho], segundos: float) -> list[Trecho]:
    """Adianta (negativo) ou atrasa (positivo) todas as legendas."""
    return [Trecho(max(0.0, t.inicio + segundos), max(0.0, t.fim + segundos), t.texto, t.falante)
            for t in trechos]
