"""Predefinições de desempenho do estúdio: rápido, equilibrado e qualidade.

Cada uma ajusta de uma vez o modelo de transcrição, os passos do OmniVoice e o uso do
processador. Sem escolha (`estudio.desempenho = "auto"`), o Optimus olha a placa de vídeo e a
memória e escolhe sozinho.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Predefinicao:
    nome: str
    descricao: str
    transcricao: str  # modelo Whisper
    passos: int  # passos do OmniVoice (mais = melhor e mais lento)
    threads: int

    def para_dict(self) -> dict:
        return asdict(self)


PREDEFINICOES = {
    "rapido": Predefinicao("rapido", "Rápido: PCs modestos ou rascunhos", "small", 16, 2),
    "equilibrado": Predefinicao("equilibrado", "Equilibrado: bom para quase tudo", "medium", 32, 4),
    "qualidade": Predefinicao("qualidade", "Qualidade máxima: placa de vídeo recomendada",
                              "large-v3-turbo", 48, 8),
}


def recomendar() -> str:
    try:
        from optimus import hardware

        hw = hardware.detectar()
    except Exception:  # noqa: BLE001
        return "equilibrado"
    if hw.placa and hw.placa.vram_gb >= 6:
        return "qualidade"
    if hw.ram_total_gb >= 12 and hw.nucleos_logicos >= 4:
        return "equilibrado"
    return "rapido"


def atual(config=None) -> Predefinicao:
    nome = str(config.get("estudio", "desempenho", "auto") if config is not None else "auto")
    nome = nome.strip().lower().replace("á", "a")
    if nome not in PREDEFINICOES:
        nome = recomendar()
    return PREDEFINICOES[nome]


def escolher(config, nome: str) -> Predefinicao:
    nome = (nome or "").strip().lower().replace("á", "a")
    if nome != "auto" and nome not in PREDEFINICOES:
        raise ValueError("Use: auto, " + ", ".join(PREDEFINICOES))
    config.definir("estudio", "desempenho", nome)
    config.salvar()
    return atual(config)
