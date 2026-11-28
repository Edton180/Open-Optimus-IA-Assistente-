"""Gerenciador de modelos do estúdio: vê o que está instalado, quanto ocupa e qual a licença,
e instala ou remove com um comando (`optimus estudio modelos`, aba Modelos ou pelo chat).

Dois tipos de item:
- **pacote**: um motor Python (OmniVoice, Chatterbox, faster-whisper, sherpa-onnx, Demucs,
  Kokoro). Instalar roda o pip do próprio Optimus.
- **arquivo**: um modelo baixado do GitHub para a pasta do estúdio (vozes Piper, Whisper
  ONNX, modelos de quem fala). Remover apaga a pasta.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from optimus.estudio import pasta_estudio
from optimus.estudio.audio import ErroEstudio


@dataclass
class Item:
    id: str
    nome: str
    tipo: str  # voz | clonagem | transcricao | isolamento | falantes
    licenca: str
    tamanho_mb: int
    descricao: str
    forma: str  # pacote | arquivo
    pacote: str = ""  # nome no pip
    modulo: str = ""  # módulo que prova que está instalado
    pastas: list[Path] = field(default_factory=list)
    baixar: Callable | None = None

    def instalado(self) -> bool:
        if self.forma == "pacote":
            from optimus.pacotes import modulo_instalado

            if not modulo_instalado(self.modulo):
                return False
            if self.id == "kokoro":  # o pacote sozinho não fala: precisa dos arquivos de voz
                from optimus.voice import tts

                return tts.kokoro_instalado()
            return True
        return bool(self.pastas) and all(p.exists() for p in self.pastas)

    def ocupado_mb(self) -> float:
        total = 0
        for p in self.pastas:
            if p.is_file():
                total += p.stat().st_size
            elif p.is_dir():
                total += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        return round(total / 1024 / 1024, 1)

    def para_dict(self) -> dict:
        return {"id": self.id, "nome": self.nome, "tipo": self.tipo, "licenca": self.licenca,
                "tamanho_mb": self.tamanho_mb, "descricao": self.descricao,
                "forma": self.forma, "pacote": self.pacote, "instalado": self.instalado(),
                "comando": _comando(self.pacote) if self.forma == "pacote" else "",
                "ocupado_mb": self.ocupado_mb() if self.forma == "arquivo" else None}


def _comando(pacote: str) -> str:
    from optimus.pacotes import comando_pip

    return comando_pip(pacote)


def catalogo() -> list[Item]:
    from optimus.estudio import diarizar, piper, transcrever

    itens = [
        Item("omnivoice", "OmniVoice", "clonagem", "Apache-2.0", 2500,
             "Clonagem, criação de voz por descrição e 600+ idiomas (modelo do Hugging Face)",
             "pacote", "omnivoice", "omnivoice"),
        Item("chatterbox", "Chatterbox Multilingual", "clonagem", "MIT", 3000,
             "Clonagem em 23 idiomas e conversor de voz (voz para voz)",
             "pacote", "chatterbox-tts", "chatterbox"),
        Item("faster-whisper", "faster-whisper", "transcricao", "MIT", 1500,
             "Transcrição mais precisa (Whisper; modelo do Hugging Face)",
             "pacote", "faster-whisper", "faster_whisper"),
        Item("sherpa-onnx", "sherpa-onnx", "transcricao", "Apache-2.0", 30,
             "Transcrição ONNX, vozes Piper e reconhecimento de quem fala",
             "pacote", "sherpa-onnx<2", "sherpa_onnx"),
        Item("demucs", "Demucs", "isolamento", "MIT", 900,
             "Separa voz, música e efeitos (karaokê, limpar a fala)",
             "pacote", "demucs>=4", "demucs"),
        Item("kokoro", "Kokoro", "voz", "MIT / Apache-2.0", 90,
             "Vozes offline do Optimus em português e outros idiomas",
             "pacote", "kokoro-onnx", "kokoro_onnx"),
    ]
    raiz_t = pasta_estudio() / "modelos" / "transcricao"
    for nome, pacote_nome, tamanho in (("small", "small", 380), ("medium", "medium", 1000),
                                       ("large-v3-turbo", "turbo", 1100)):
        pasta = raiz_t / f"sherpa-onnx-whisper-{pacote_nome}"
        itens.append(Item(f"whisper-{nome}", f"Whisper {nome} (ONNX)", "transcricao", "MIT",
                          tamanho, "Modelo de transcrição para o sherpa-onnx (do GitHub)",
                          "arquivo", pastas=[pasta],
                          baixar=lambda p=None, n=nome: transcrever._modelo_sherpa(n, p)))
    itens.append(Item("quem-fala", "Modelos de quem fala", "falantes", "MIT / Apache-2.0", 40,
                      "Separa as falas por pessoa (segmentação pyannote + impressão de voz)",
                      "arquivo", pastas=[diarizar._segmentacao(), diarizar._impressao()],
                      baixar=lambda p=None: diarizar.baixar_modelos(p)))
    for v in piper.VOZES:
        itens.append(Item(f"piper-{v.id}", v.nome, "voz", v.licenca, v.tamanho_mb,
                          f"Voz Piper offline ({v.idioma})", "arquivo",
                          pastas=[piper.pasta_voz(v)],
                          baixar=lambda p=None, i=v.id: piper.baixar(i, p)))
    return itens


def obter(ident: str) -> Item:
    for item in catalogo():
        if item.id == ident or item.nome.lower() == ident.lower():
            return item
    raise ErroEstudio(f"Modelo desconhecido: {ident}. Veja a lista: optimus estudio modelos")


def listar() -> list[dict]:
    return [i.para_dict() for i in catalogo()]


def _pip(*argumentos: str) -> str:
    r = subprocess.run([sys.executable, "-m", "pip", *argumentos], capture_output=True,
                       timeout=3600, check=False)
    saida = (r.stdout + r.stderr).decode("utf-8", "replace")
    if r.returncode != 0:
        raise ErroEstudio("O pip falhou:\n" + saida[-1500:])
    return saida


def instalar(ident: str, progresso=None) -> dict:
    item = obter(ident)
    if item.forma == "pacote":
        (progresso or (lambda *a: None))(0.05, f"Instalando {item.nome} (pip)…")
        _pip("install", item.pacote)
        importlib.invalidate_caches()
    elif item.baixar:
        item.baixar(progresso)
    if item.id == "kokoro":
        from optimus.voice import tts

        tts.baixar_kokoro(progresso)
    if not item.instalado():  # nunca dizer que instalou sem conferir
        if item.forma == "pacote":
            from optimus.pacotes import python_do_optimus

            raise ErroEstudio(f"O pip terminou, mas o Optimus ainda não encontra {item.nome} "
                              f"(módulo {item.modulo}) no Python {python_do_optimus()}. "
                              "Feche e abra o Optimus; se continuar, instale com: "
                              + _comando(item.pacote))
        raise ErroEstudio(f"O download de {item.nome} terminou incompleto. Tente de novo.")
    return item.para_dict()


def remover(ident: str) -> dict:
    item = obter(ident)
    if item.forma == "pacote":
        nome = item.pacote.split("<")[0].split(">")[0].split("=")[0]
        _pip("uninstall", "-y", nome)
    else:
        for p in item.pastas:
            alvo = p.parent if item.id == "quem-fala" and p.name == "model.onnx" else p
            if alvo.is_dir():
                shutil.rmtree(alvo, ignore_errors=True)
            elif alvo.exists():
                alvo.unlink()
        if item.id.startswith("piper-"):
            from optimus.estudio import piper

            piper.descarregar()
    return item.para_dict()
