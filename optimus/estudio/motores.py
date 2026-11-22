"""Geração de voz do estúdio: transforma texto em áudio com qualquer perfil e idioma.

- Vozes prontas em português do Brasil: os motores do Optimus (Kokoro offline, Edge online,
  ElevenLabs e a voz do sistema).
- Outros idiomas sem clonagem: vozes neurais do Edge daquele idioma (online) ou do Kokoro.
- Vozes clonadas: Chatterbox Multilingual (licença MIT, 23 idiomas, inclusive português). A
  amostra em português do Brasil faz a voz sair com sotaque brasileiro. Opcional: `pip install
  chatterbox-tts` (baixa o modelo na primeira vez; com placa de vídeo fica bem mais rápido).
- Conversor de voz (voz para voz): Chatterbox VC, mantém a fala e troca o timbre.

Depois da síntese aplicam-se tom, ritmo e efeito do perfil, e o dicionário de pronúncia vale
antes de tudo.
"""

from __future__ import annotations

import re
import tempfile
import threading
from pathlib import Path

from optimus.estudio import audio, idiomas, pronuncia
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.vozes import Perfil, obter

TAXA = 24000
_MODELOS: dict[str, object] = {}
_TRAVA = threading.Lock()

# Vozes do Kokoro em outros idiomas (offline), quando não há internet para o Edge.
_KOKORO_OUTROS = {
    "en-us": ("af_heart", "am_adam"), "en-gb": ("bf_emma", "bm_george"),
    "es": ("ef_dora", "em_alex"), "fr-fr": ("ff_siwis", "ff_siwis"),
    "it": ("if_sara", "im_nicola"), "ja": ("jf_alpha", "jm_kumo"),
    "zh": ("zf_xiaobei", "zm_yunjian"), "hi": ("hf_alpha", "hm_omega"),
    "pt-br": ("pf_dora", "pm_alex"),
}


# ---------------------------------------------------------------------- utilidades
def dispositivo() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


def clonagem_instalada() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("chatterbox") is not None
    except (ImportError, ValueError):
        return False


def dividir_texto(texto: str, maximo: int = 280) -> list[str]:
    """Frases de até `maximo` caracteres (motores de voz se perdem em textos longos)."""
    frases = [f.strip() for f in re.split(r"(?<=[.!?…;:])\s+|\n+", texto) if f.strip()]
    saida, atual = [], ""
    for f in frases:
        while len(f) > maximo:  # frase enorme sem pontuação: corta na vírgula ou espaço
            corte = max(f.rfind(",", 0, maximo), f.rfind(" ", 0, maximo))
            corte = corte if corte > maximo // 3 else maximo
            saida.append(f[:corte + 1].strip())
            f = f[corte + 1:].strip()
        if atual and len(atual) + 1 + len(f) > maximo:
            saida.append(atual)
            atual = f
        else:
            atual = f"{atual} {f}".strip()
    if atual:
        saida.append(atual)
    return saida


def _decodificar(dados: bytes, formato: str):
    if not dados:
        return None
    if formato == "wav":
        x, taxa = audio.ler_wav(dados)
        if taxa == TAXA:
            return x
    with tempfile.NamedTemporaryFile(suffix="." + formato, delete=False) as f:
        f.write(dados)
        nome = f.name
    try:
        return audio.carregar(nome, TAXA)
    finally:
        Path(nome).unlink(missing_ok=True)


def mudar_tom(amostras, taxa: int, semitons: float):
    """Tom mais grave (negativo) ou agudo (positivo), sem mudar a duração."""
    import numpy as np

    if abs(semitons) < 0.05 or not len(amostras):
        return amostras
    fator = 2 ** (semitons / 12)
    bruto = audio._rodar(["-f", "wav", "-i", "-", "-filter:a",
                          f"asetrate={int(taxa * fator)},aresample={taxa},"
                          f"{audio._cadeia_atempo(1 / fator)}",
                          "-ac", "1", "-ar", str(taxa), "-f", "f32le", "-"],
                         entrada=audio.wav_bytes(amostras, taxa))
    return np.frombuffer(bruto, dtype="<f4").copy()


def _pos(amostras, perfil: Perfil, ritmo_extra: float = 1.0):
    from optimus.voice.tts import aplicar_efeito

    x = amostras
    if perfil.tom:
        x = mudar_tom(x, TAXA, perfil.tom)
    fator = (perfil.velocidade or 1.0) * (ritmo_extra or 1.0)
    if perfil.motor == "clone" and abs(fator - 1) > 0.01:
        x = audio.esticar(x, TAXA, fator)  # o Chatterbox não tem controle de ritmo
    if perfil.efeito:
        x = aplicar_efeito(x, TAXA, perfil.efeito)
    return x


# ---------------------------------------------------------------------- motores
def _falante(perfil: Perfil, velocidade: float, config):
    from optimus.voice import tts

    return tts.Falante(perfil.base or perfil.id, velocidade=velocidade, config=config)


def _gerar_padrao(texto: str, perfil: Perfil, velocidade: float, config):
    falante = _falante(perfil, velocidade * (perfil.velocidade or 1.0), config)
    falante.efeito = ""  # o efeito do perfil é aplicado depois, uma vez só
    dados, formato = falante.sintetizar(texto)
    return _decodificar(dados, formato)


def _gerar_outro_idioma(texto: str, perfil: Perfil, idioma: idiomas.Idioma, velocidade: float):
    """Idioma diferente do português sem clonagem: Edge (online) ou Kokoro (offline)."""
    import asyncio

    voz_edge = idiomas.voz_edge(idioma, perfil.genero)
    taxa = f"{int(round((velocidade * (perfil.velocidade or 1) - 1) * 100)):+d}%"
    try:
        import edge_tts

        async def gerar() -> bytes:
            partes = []
            async for p in edge_tts.Communicate(texto, voz_edge, rate=taxa).stream():
                if p["type"] == "audio":
                    partes.append(p["data"])
            return b"".join(partes)

        resultado: list[bytes] = []

        def rodar() -> None:
            try:
                resultado.append(asyncio.run(gerar()))
            except Exception:  # noqa: BLE001 - sem internet: cai no Kokoro abaixo
                pass

        linha = threading.Thread(target=rodar, daemon=True)
        linha.start()
        linha.join()
        if resultado and resultado[0]:
            return _decodificar(resultado[0], "mp3")
    except Exception:  # noqa: BLE001
        pass
    if idioma.kokoro in _KOKORO_OUTROS:
        from optimus.voice import tts

        if tts.kokoro_instalado():
            from kokoro_onnx import Kokoro

            chave = "kokoro"
            with _TRAVA:
                if chave not in _MODELOS:
                    _MODELOS[chave] = Kokoro(str(tts.pasta_vozes() / tts.ARQUIVOS_KOKORO[0]),
                                             str(tts.pasta_vozes() / tts.ARQUIVOS_KOKORO[1]))
            f, m = _KOKORO_OUTROS[idioma.kokoro]
            x, taxa_k = _MODELOS[chave].create(
                texto, voice=m if perfil.genero.startswith("m") else f,
                speed=velocidade * (perfil.velocidade or 1), lang=idioma.kokoro)
            return _decodificar(audio.wav_bytes(x, taxa_k), "wav")
    raise ErroEstudio(f"Sem voz para {idioma.nome} agora: precisa de internet (vozes Edge) "
                      "ou de uma voz clonada (pip install chatterbox-tts).")


def _modelo_clone():
    if not clonagem_instalada():
        raise ErroEstudio("A clonagem de voz precisa do motor Chatterbox: "
                          "pip install chatterbox-tts (cerca de 3 GB com o modelo).")
    with _TRAVA:
        if "clone" not in _MODELOS:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            _MODELOS["clone"] = ChatterboxMultilingualTTS.from_pretrained(device=dispositivo())
    return _MODELOS["clone"]


def _para_numpy(onda, taxa_origem: int):
    import numpy as np

    try:
        x = onda.squeeze().detach().cpu().numpy()
    except AttributeError:
        x = np.asarray(onda).squeeze()
    x = np.asarray(x, dtype="float32")
    if taxa_origem != TAXA:
        bruto = audio._rodar(["-f", "wav", "-i", "-", "-ar", str(TAXA), "-ac", "1",
                              "-f", "f32le", "-"], entrada=audio.wav_bytes(x, taxa_origem))
        x = np.frombuffer(bruto, dtype="<f4").copy()
    return x


def _gerar_clone(texto: str, perfil: Perfil, idioma: idiomas.Idioma):
    amostra = perfil.caminho_amostra()
    if not amostra or not amostra.exists():
        raise ErroEstudio(f"A amostra da voz '{perfil.nome}' sumiu. Clone de novo.")
    if not idioma.clone:
        raise ErroEstudio(f"A clonagem ainda não fala {idioma.nome}.")
    modelo = _modelo_clone()
    expr = float(perfil.expressividade if perfil.expressividade is not None else 0.5)
    onda = modelo.generate(texto, language_id=idioma.clone, audio_prompt_path=str(amostra),
                           exaggeration=expr, cfg_weight=0.3 if expr > 0.7 else 0.5)
    return _para_numpy(onda, getattr(modelo, "sr", TAXA))


# ---------------------------------------------------------------------- API pública
def gerar(texto: str, voz: str | Perfil = "", idioma: str = "", velocidade: float = 1.0,
          config=None, cancelado=None):
    """Texto → numpy float32 mono a 24 kHz. Textos longos são gerados por frases e unidos
    com pausas naturais."""
    import numpy as np

    perfil = voz if isinstance(voz, Perfil) else obter(voz)
    lingua = idiomas.idioma(idioma or perfil.idioma)
    texto = pronuncia.aplicar(texto.strip(), lingua.codigo)
    if not texto:
        raise ErroEstudio("Texto vazio.")
    pausa = np.zeros(int(TAXA * 0.22), dtype="float32")
    pedacos = []
    for frase in dividir_texto(texto):
        if cancelado and cancelado():
            raise ErroEstudio("Cancelado.")
        if perfil.motor == "clone":
            x = _gerar_clone(frase, perfil, lingua)
        elif lingua.codigo == "pt-BR":
            x = _gerar_padrao(frase, perfil, velocidade, config)
        else:
            x = _gerar_outro_idioma(frase, perfil, lingua, velocidade)
        if x is None or not len(x):
            continue
        pedacos += [audio.cortar_silencio(x, TAXA), pausa]
    if not pedacos:
        raise ErroEstudio("O motor de voz não devolveu áudio.")
    junto = np.concatenate(pedacos[:-1])
    ritmo = velocidade if perfil.motor == "clone" else 1.0
    return audio.normalizar(_pos(junto, perfil, ritmo))


def converter(entrada: str | Path, voz: str | Perfil, config=None):
    """Troca o timbre de uma gravação pelo de outra voz, mantendo a fala, o ritmo e a emoção.

    A voz de destino pode ser clonada (usa a amostra) ou pronta (o Optimus gera uma amostra
    curta com ela)."""
    perfil = voz if isinstance(voz, Perfil) else obter(voz)
    if not clonagem_instalada():
        raise ErroEstudio("O conversor de voz precisa do Chatterbox: pip install chatterbox-tts")
    alvo = perfil.caminho_amostra()
    temporario = None
    if not alvo or not alvo.exists():
        frase = ("Olá! Esta é uma amostra da minha voz, gravada para servir de referência. "
                 "Falo de forma clara, natural e no meu ritmo de sempre.")
        x = gerar(frase, perfil, "pt-BR", config=config)
        temporario = Path(tempfile.mkstemp(suffix=".wav")[1])
        audio.salvar(x, TAXA, temporario, marca_ia=False)
        alvo = temporario
    fonte = Path(tempfile.mkstemp(suffix=".wav")[1])
    try:
        audio.salvar(audio.carregar(entrada, TAXA), TAXA, fonte, marca_ia=False)
        with _TRAVA:
            if "vc" not in _MODELOS:
                from chatterbox.vc import ChatterboxVC

                _MODELOS["vc"] = ChatterboxVC.from_pretrained(dispositivo())
        modelo = _MODELOS["vc"]
        onda = modelo.generate(audio=str(fonte), target_voice_path=str(alvo))
        return audio.normalizar(_para_numpy(onda, getattr(modelo, "sr", TAXA)))
    finally:
        fonte.unlink(missing_ok=True)
        if temporario:
            temporario.unlink(missing_ok=True)


def descarregar() -> int:
    """Tira os modelos de voz da memória (útil depois de uma dublagem longa)."""
    with _TRAVA:
        n = len(_MODELOS)
        _MODELOS.clear()
    try:
        import gc

        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass
    return n
