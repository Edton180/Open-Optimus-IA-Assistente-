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


class _InstalacaoCancelada(Exception):
    """Interrompe o lote sem registrar cancelamento como falha de um modelo."""


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
            try:
                presente = importlib.util.find_spec(self.modulo) is not None
            except (ImportError, ValueError):
                return False
            # Pacote instalado sem os pesos não é um motor pronto para uso offline.
            if self.id in {"omnivoice", "chatterbox", "faster-whisper", "demucs", "kokoro"}:
                return presente and _marcador(self.id).is_file()
            return presente
        if self.id.startswith("whisper-"):
            pasta = self.pastas[0] if self.pastas else None
            return bool(pasta and pasta.is_dir()
                        and (list(pasta.glob("*-tokens.txt")) or (pasta / "tokens.txt").is_file())
                        and list(pasta.glob("*encoder*.onnx"))
                        and list(pasta.glob("*decoder*.onnx")))
        if self.id.startswith("piper-"):
            pasta = self.pastas[0] if self.pastas else None
            # O catálogo legado considera o arquivo ONNX como marcador do download da voz;
            # tokens/espeak são verificados pelo motor sherpa-onnx ao inicializar a síntese.
            return bool(pasta and pasta.is_dir() and any(pasta.glob("*.onnx")))
        return bool(self.pastas) and all(p.is_file() and p.stat().st_size > 0
                                         for p in self.pastas)

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
                "ocupado_mb": self.ocupado_mb() if self.forma == "arquivo" else None}


def _marcador(ident: str) -> Path:
    return pasta_estudio() / "modelos" / ".prontos" / f"{ident}.ok"


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


class _InstalacaoCancelada(Exception):
    """Sinal interno para interromper a instalação em lote sem registrar falha."""


def instalar(ident: str, progresso=None, cancelado=None) -> dict:
    def verificar_cancelamento():
        if cancelado and cancelado():
            raise _InstalacaoCancelada("Instalação cancelada pelo usuário.")

    def atualizar(pct, msg):
        verificar_cancelamento()
        if progresso:
            progresso(pct, msg)

    verificar_cancelamento()
    item = obter(ident)
    if item.forma == "pacote":
        atualizar(0.05, f"Instalando {item.nome} (pip)…")
        _pip("install", item.pacote)
        verificar_cancelamento()
        importlib.invalidate_caches()
        # Pré-carrega os pesos agora, não apenas na primeira utilização do recurso.
        if item.id in {"omnivoice", "chatterbox", "faster-whisper"}:
            try:
                from huggingface_hub import snapshot_download
            except ImportError:
                _pip("install", "huggingface_hub>=0.24")
                from huggingface_hub import snapshot_download

            verificar_cancelamento()
            repositorios = {
                "omnivoice": "k2-fsa/OmniVoice",
                "chatterbox": "ResembleAI/chatterbox",
                "faster-whisper": "Systran/faster-whisper-small",
            }
            snapshot_download(repo_id=repositorios[item.id])
            verificar_cancelamento()
        elif item.id == "demucs":
            # O Demucs baixa o checkpoint oficial e o deixa no cache do torch hub.
            from demucs.pretrained import get_model

            verificar_cancelamento()
            get_model(name="htdemucs")
            verificar_cancelamento()
        elif item.id == "kokoro":
            from optimus.voice import tts

            if not tts.baixar_kokoro(atualizar):
                raise ErroEstudio("Não foi possível baixar os pesos do Kokoro.")
        if item.id in {"omnivoice", "chatterbox", "faster-whisper", "demucs", "kokoro"}:
            marcador = _marcador(item.id)
            marcador.parent.mkdir(parents=True, exist_ok=True)
            marcador.write_text("ok", encoding="utf-8")
    elif item.baixar:
        item.baixar(atualizar if progresso or cancelado else None)
        verificar_cancelamento()
    return item.para_dict()



def instalar_todos(progresso=None, ids: list[str] | None = None, cancelado=None) -> dict:
    """Instala sequencialmente todos os motores e pesos do catálogo.

    Faz uma pré-verificação de espaço, preserva os itens já instalados e continua
    após falhas individuais para não perder o progresso dos demais downloads.
    """
    itens = catalogo()
    selecionados = [i for i in itens if ids is None or i.id in set(ids)]
    faltantes = [i for i in selecionados if not i.instalado()]
    estimativa = sum(i.tamanho_mb for i in faltantes)
    # Em perfis recém-criados a pasta ainda não existe; disk_usage exige um caminho existente.
    diretorio_estudio = pasta_estudio()
    diretorio_estudio.mkdir(parents=True, exist_ok=True)
    livre = shutil.disk_usage(diretorio_estudio).free // (1024 * 1024)
    reserva = max(1024, int(estimativa * 0.25))
    necessario = estimativa + reserva
    if livre < necessario:
        raise ErroEstudio(
            f"Espaço insuficiente para instalar os modelos: estimativa de {estimativa} MB "
            f"+ reserva de {reserva} MB; disponíveis {livre} MB. Libere espaço ou instale "
            "os modelos individualmente."
        )
    resultados = []
    total = max(1, len(selecionados))
    def verificar_cancelamento():
        if cancelado and cancelado():
            raise _InstalacaoCancelada()

    def retornar_cancelado():
        return {"total": len(resultados), "instalados": sum(
            r["estado"] in {"instalado", "já instalado"} for r in resultados),
            "cancelado": True, "resultados": resultados}

    for indice, item in enumerate(selecionados, 1):
        if cancelado and cancelado():
            return retornar_cancelado()
        if item.instalado():
            resultados.append({"id": item.id, "nome": item.nome, "estado": "já instalado"})
            continue
        if progresso:
            progresso((indice - 1) / total, f"({indice}/{total}) Instalando {item.nome}…")
        try:
            def callback(pct, msg):
                verificar_cancelamento()
                if progresso:
                    progresso(((indice - 1) + max(0.0, min(1.0, float(pct)))) / total, msg)

            resultado = instalar(item.id, callback if progresso or cancelado else None,
                                 cancelado=cancelado)
            resultados.append({"id": item.id, "nome": item.nome, "estado": "instalado",
                                "detalhes": resultado})
            verificar_cancelamento()
        except _InstalacaoCancelada:
            return retornar_cancelado()
        except Exception as erro:  # cada falha fica registrada; os outros modelos continuam
            resultados.append({"id": item.id, "nome": item.nome, "estado": "falhou",
                                "erro": f"{type(erro).__name__}: {erro}"})
    falhas = [r for r in resultados if r["estado"] == "falhou"]
    if progresso:
        progresso(1.0, f"Instalação concluída: {len(resultados) - len(falhas)}/{len(resultados)}")
    return {"total": len(resultados), "instalados": len(resultados) - len(falhas),
            "falhas": falhas, "resultados": resultados}

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
