"""Marcas de expressão no texto, iguais em todos os motores de voz.

    Olá! [pausa 1,5] Tudo bem? [risada] Que bom.

- `[pausa]` ou `[pausa 2]` / `[pausa 1,5s]`: silêncio (padrão 0,6 s, até 10 s).
- `[risada]`, `[suspiro]`, `[respiração]`, `[tosse]`, `[choro]`, `[bocejo]`, `[hum]`: sons sem
  palavras. O OmniVoice faz o som de verdade; nos outros motores a marca é tirada, para não
  ser lida em voz alta.
"""

from __future__ import annotations

import re

from optimus.estudio.omnivoice import SONS, _normal

_PAUSA = re.compile(r"\[\s*(?:pausa|pause|sil[eê]ncio)\s*(\d+(?:[.,]\d+)?)?\s*s?\s*\]",
                    re.IGNORECASE)
_SOM = re.compile(r"\[([^\]\d]{2,20})\]")
PAUSA_PADRAO = 0.6


def partes(texto: str) -> list[tuple[str, float]]:
    """[(texto, pausa_depois_em_segundos)]."""
    saida: list[tuple[str, float]] = []
    inicio = 0
    for m in _PAUSA.finditer(texto):
        segundos = float((m.group(1) or str(PAUSA_PADRAO)).replace(",", "."))
        saida.append((texto[inicio:m.start()].strip(), min(10.0, segundos)))
        inicio = m.end()
    saida.append((texto[inicio:].strip(), 0.0))
    return [(t, p) for t, p in saida if t or p]


def tem_som(texto: str) -> bool:
    return any(_normal(m.group(1)).strip() in SONS for m in _SOM.finditer(texto))


def sem_sons(texto: str) -> str:
    """Tira as marcas de som (para motores que leriam "risada" em voz alta)."""
    limpo = _SOM.sub(lambda m: "" if _normal(m.group(1)).strip() in SONS else m.group(0), texto)
    return re.sub(r"\s{2,}", " ", limpo).strip()
