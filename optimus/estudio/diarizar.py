"""Quem falou quando (diarização), offline, com o sherpa-onnx (Apache-2.0).

Modelos baixados na primeira vez (cerca de 35 MB), do GitHub do sherpa-onnx:
- segmentação pyannote 3.0 (MIT);
- impressão de voz CAM++ do 3D-Speaker (Apache-2.0).

Usado para legendas com o nome de quem fala e para dublar cada pessoa com uma voz própria.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from optimus.estudio import audio, pasta_estudio
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho

_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
URL_SEGMENTACAO = _BASE + ("speaker-segmentation-models/"
                           "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")
URL_IMPRESSAO = _BASE + ("speaker-recongition-models/"
                         "3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx")
TAXA = 16000


def pasta_modelos() -> Path:
    return pasta_estudio() / "modelos" / "diarizacao"


def _segmentacao() -> Path:
    return pasta_modelos() / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"


def _impressao() -> Path:
    return pasta_modelos() / "campplus.onnx"


def instalado() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("sherpa_onnx") is not None
    except (ImportError, ValueError):
        return False


def modelos_prontos() -> bool:
    return _segmentacao().exists() and _impressao().exists()


def baixar_modelos(progresso=None) -> None:
    import httpx

    pasta = pasta_modelos()
    pasta.mkdir(parents=True, exist_ok=True)
    if not _segmentacao().exists():
        (progresso or (lambda *a: None))(0.1, "Baixando o modelo de segmentação…")
        pacote = pasta / "segmentacao.tar.bz2"
        with httpx.stream("GET", URL_SEGMENTACAO, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with open(pacote, "wb") as f:
                f.writelines(r.iter_bytes())
        with tarfile.open(pacote) as tar:
            raiz = pasta.resolve()
            for membro in tar.getmembers():  # nada de sair da pasta (zip-slip)
                destino = (pasta / membro.name).resolve()
                if not destino.is_relative_to(raiz) or membro.issym() or membro.islnk():
                    raise ErroEstudio("Pacote do modelo de segmentação inválido.")
            tar.extractall(pasta)  # conferido acima
        pacote.unlink(missing_ok=True)
    if not _impressao().exists():
        (progresso or (lambda *a: None))(0.5, "Baixando o modelo de impressão de voz…")
        temporario = _impressao().with_suffix(".parcial")
        with httpx.stream("GET", URL_IMPRESSAO, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with open(temporario, "wb") as f:
                f.writelines(r.iter_bytes())
        temporario.replace(_impressao())


def falantes(arquivo: str | Path, quantos: int = 0, limiar: float = 0.5,
             progresso=None) -> list[Trecho]:
    """Devolve trechos (início, fim, falante) com falantes "Pessoa 1", "Pessoa 2"...

    `quantos`: número de pessoas, se você souber (0 = descobrir sozinho)."""
    if not instalado():
        raise ErroEstudio("Para saber quem falou quando, instale: pip install sherpa-onnx")
    if not modelos_prontos():
        baixar_modelos(progresso)
    import sherpa_onnx

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(_segmentacao()))),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(_impressao())),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=quantos or -1,
                                                    threshold=limiar),
        min_duration_on=0.3, min_duration_off=0.5)
    if not config.validate():
        raise ErroEstudio("Configuração da diarização inválida (modelos corrompidos?).")
    sd = sherpa_onnx.OfflineSpeakerDiarization(config)
    amostras = audio.carregar(arquivo, sd.sample_rate or TAXA)
    (progresso or (lambda *a: None))(0.7, "Separando quem fala…")
    resultado = sd.process(amostras).sort_by_start_time()
    ordem: dict[int, str] = {}
    saida = []
    for r in resultado:
        nome = ordem.setdefault(r.speaker, f"Pessoa {len(ordem) + 1}")
        saida.append(Trecho(round(r.start, 3), round(r.end, 3), "", nome))
    return saida


def atribuir(trechos: list[Trecho], turnos: list[Trecho]) -> list[Trecho]:
    """Põe em cada trecho da transcrição o falante que mais fala durante ele."""
    saida = []
    for t in trechos:
        melhor, sobreposicao = "", 0.0
        for v in turnos:
            s = min(t.fim, v.fim) - max(t.inicio, v.inicio)
            if s > sobreposicao:
                melhor, sobreposicao = v.falante, s
        if not melhor and turnos:  # sem sobreposição: o turno mais próximo
            melhor = min(turnos, key=lambda v: abs(v.inicio - t.inicio)).falante
        saida.append(Trecho(t.inicio, t.fim, t.texto, melhor or t.falante))
    return saida
