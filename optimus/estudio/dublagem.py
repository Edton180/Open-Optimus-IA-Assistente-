"""Legendar e dublar vídeos (e áudios): transcrever → traduzir → falar → sincronizar → juntar.

    dublar("aula.mp4", destino="pt-BR", voz="Mordomo")
    dublar("entrevista.mp4", destino="pt-BR", voz_original=True, consentimento=True)
    legendar("video.mp4", destino="en-US", queimar=True)

- `voz_original=True` clona a voz de quem fala no próprio vídeo (precisa de consentimento e
  do motor de clonagem), e a dublagem sai com a mesma voz no outro idioma.
- Cada trecho falado é guardado: se a dublagem parar no meio, recomeça de onde parou.
- Dá para revisar a legenda traduzida e dublar a partir dela (`legenda_pronta="x.srt"`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from optimus.estudio import (
    audio,
    idiomas,
    legendas,
    motores,
    pasta_estudio,
    pasta_saidas,
    registrar,
    traduzir,
    transcrever,
    vozes,
)
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho

TAXA = motores.TAXA


def _hash(*partes) -> str:
    return hashlib.sha1("|".join(str(p) for p in partes).encode()).hexdigest()[:12]


def _assinatura(arquivo: Path) -> str:
    st = arquivo.stat()
    return _hash(arquivo.resolve(), st.st_size, int(st.st_mtime))


def _nada(*_a, **_k):
    return None


def _etapa(progresso, inicio: float, fim: float):
    """Converte o progresso de uma etapa (0..1) para a faixa total [inicio, fim]."""
    def rep(valor: float, mensagem: str = "") -> None:
        (progresso or _nada)(inicio + (fim - inicio) * valor, mensagem)
    return rep


def _obter_trechos(arquivo: Path, origem: str, config, progresso, cancelado,
                   pasta: Path, falantes: bool = False) -> tuple[list[Trecho], idiomas.Idioma]:
    cache = pasta / ("original-falantes.json" if falantes else "original.json")
    if cache.exists():
        dados = json.loads(cache.read_text(encoding="utf-8"))
        return [Trecho(**t) for t in dados["trechos"]], idiomas.idioma(dados["idioma"])
    trechos, falado = transcrever.transcrever(arquivo, origem, config=config,
                                              progresso=progresso, cancelado=cancelado)
    if not trechos:
        raise ErroEstudio("Não ouvi fala nenhuma nesse arquivo.")
    trechos = legendas.dividir_longos(trechos)
    if falantes:
        from optimus.estudio import diarizar

        (progresso or _nada)(0.95, "Descobrindo quem fala…")
        trechos = diarizar.atribuir(trechos, diarizar.falantes(arquivo))
    cache.write_text(json.dumps({"idioma": falado.codigo,
                                 "trechos": [t.para_dict() for t in trechos]},
                                ensure_ascii=False), encoding="utf-8")
    return trechos, falado


def _traduzidos(trechos, falado, destino, llm, projeto, para_dublagem, progresso, cancelado,
                pasta: Path) -> list[Trecho]:
    if falado.codigo == destino.codigo or (falado.whisper == destino.whisper
                                           and destino.codigo == "pt-BR"):
        return trechos
    if llm is None:
        raise ErroEstudio("Para traduzir preciso do modelo de IA do Optimus.")
    # o glossário entra na chave: mudou o projeto ou as regras, traduz de novo
    gl = traduzir.glossario(projeto) if projeto else {}
    regras = hashlib.sha1(json.dumps([projeto, gl], sort_keys=True, ensure_ascii=False)
                          .encode()).hexdigest()[:8]
    marca = "-dub" if para_dublagem else ""
    marca += "-f" if any(t.falante for t in trechos) else ""
    cache = pasta / f"traducao-{destino.codigo}{marca}-{regras}.json"
    if cache.exists():
        return [Trecho(**t) for t in json.loads(cache.read_text(encoding="utf-8"))]
    novos = traduzir.traduzir(trechos, destino.codigo, llm, falado.codigo, projeto,
                              para_dublagem, progresso, cancelado)
    cache.write_text(json.dumps([t.para_dict() for t in novos], ensure_ascii=False),
                     encoding="utf-8")
    return novos


def _pasta_trabalho(arquivo: Path) -> Path:
    pasta = pasta_estudio() / "trabalhos" / f"{arquivo.stem[:30]}-{_assinatura(arquivo)}"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


# ---------------------------------------------------------------------- legendar
def legendar(arquivo: str | Path, destino: str = "", origem: str = "", formato: str = "srt",
             queimar: bool = False, embutir: bool = False, llm=None, projeto: str = "",
             estilo: str = "", config=None, progresso=None, cancelado=None,
             saida: str | Path | None = None, falantes: bool = False) -> dict:
    """Gera a legenda do vídeo/áudio (no idioma falado ou traduzida) e, se pedir, põe no
    vídeo: queimada na imagem (aparece em qualquer lugar) ou como faixa (liga e desliga).
    `falantes=True` põe o nome de quem fala ("Pessoa 1: ...")."""
    arquivo = Path(arquivo)
    pasta = _pasta_trabalho(arquivo)
    trechos, falado = _obter_trechos(arquivo, origem, config, _etapa(progresso, 0, 0.6),
                                     cancelado, pasta, falantes=falantes)
    alvo = idiomas.idioma(destino) if destino else falado
    trechos = _traduzidos(trechos, falado, alvo, llm, projeto, False,
                          _etapa(progresso, 0.6, 0.85), cancelado, pasta)
    for t in trechos:
        t.texto = legendas.quebrar_linhas(t.texto)
    destino_dir = Path(saida) if saida else pasta_saidas(config)
    arquivos = [str(legendas.salvar(trechos, destino_dir / f"{arquivo.stem}.{alvo.codigo}.{f}",
                                    com_falante=falantes))
                for f in sorted({formato.lower().lstrip("."), "srt"})]
    resultado = {"legendas": sorted(arquivos), "idioma_falado": falado.nome,
                 "idioma_legenda": alvo.nome, "trechos": len(trechos)}
    if (queimar or embutir) and audio.eh_video(arquivo):
        (progresso or _nada)(0.9, "Colocando a legenda no vídeo…")
        srt = next(a for a in arquivos if a.endswith(".srt"))
        video = destino_dir / f"{arquivo.stem}.legendado.{alvo.codigo}{arquivo.suffix}"
        audio.juntar_video(arquivo, video, legenda=srt, queimar=queimar,
                           estilo=estilo or audio.estilo_legenda())
        resultado["video"] = str(video)
    registrar("legenda", resultado.get("video") or arquivos[0], idioma=alvo.codigo)
    return resultado


# ---------------------------------------------------------------------- dublar
def amostra_da_fala(trechos: list[Trecho], som, taxa: int, alvo: float = 20.0):
    """Junta os trechos mais longos de fala (até ~20 s) para clonar a voz original."""
    import numpy as np

    escolhidos, total = [], 0.0
    for t in sorted(trechos, key=lambda t: t.duracao, reverse=True):
        if total >= alvo:
            break
        if t.duracao >= 1.5:
            escolhidos.append(t)
            total += t.duracao
    if total < vozes.MIN_AMOSTRA:
        raise ErroEstudio("Não há fala limpa suficiente no vídeo para clonar a voz.")
    partes = [som[int(t.inicio * taxa): int(t.fim * taxa)] for t in
              sorted(escolhidos, key=lambda t: t.inicio)]
    return np.concatenate(partes)


def _faixa_dublada(trechos: list[Trecho], elenco: dict, idioma: idiomas.Idioma,
                   duracao: float, pasta: Path, config, progresso, cancelado):
    """`elenco`: {falante: perfil}; a chave "" é a voz de quem não tem falante."""
    pedacos = []
    ajustes = []
    for n, t in enumerate(trechos):
        if cancelado and cancelado():
            raise ErroEstudio("Cancelado.")
        perfil = elenco.get(t.falante) or elenco[""]
        proximo = trechos[n + 1].inicio if n + 1 < len(trechos) else duracao or t.fim + 2.0
        espaco = max(t.duracao, proximo - t.inicio - 0.05)
        # O OmniVoice já gera a fala com o tempo do trecho original; os outros são ajustados
        alvo = round(min(t.duracao, espaco), 2) if t.duracao >= 0.4 else 0.0
        chave = _hash(t.texto, perfil.id, perfil.tom, perfil.velocidade, idioma.codigo, alvo)
        cache = pasta / "falas" / f"{n:05d}-{chave}.wav"
        if cache.exists():
            x, _ = audio.ler_wav(cache.read_bytes())
        else:
            x = motores.gerar(t.texto, perfil, idioma.codigo, config=config, cancelado=cancelado,
                              duracao=alvo)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(audio.wav_bytes(x, TAXA))
        x, fator = audio.caber(x, TAXA, espaco)
        if fator > 1.01:
            ajustes.append(n)
        pedacos.append((t.inicio, x))
        (progresso or _nada)((n + 1) / len(trechos), f"Dublando… {n + 1} de {len(trechos)}")
    return audio.linha_do_tempo(pedacos, TAXA, duracao), ajustes


VOZES_ELENCO = ["valkyrie", "prime", "aurora", "nexus", "lyra", "titan", "mordomo"]


def _montar_elenco(trechos: list[Trecho], originais: list[Trecho], voz: str,
                   elenco: dict[str, str] | None, voz_original: bool, consentimento: bool,
                   arquivo: Path, alvo: idiomas.Idioma, pasta: Path, p) -> dict:
    nomes = list(dict.fromkeys(t.falante for t in trechos if t.falante))
    padrao = vozes.obter(voz) if voz else vozes.obter("valkyrie")
    saida: dict = {"": padrao}
    if voz_original:
        if not consentimento:
            raise ErroEstudio("Para dublar com a voz de quem fala no vídeo, confirme que é você "
                              "ou que tem autorização de cada pessoa (consentimento=true).")
        p(0.46, "Clonando a voz original…")
        som = audio.carregar(arquivo, vozes.TAXA_AMOSTRA)
        for quem in nomes or [""]:
            deles = [t for t in originais if t.falante == quem] if quem else originais
            try:
                amostra = pasta / f"voz-original{('-' + quem) if quem else ''}.wav"
                audio.salvar(amostra_da_fala(deles, som, vozes.TAXA_AMOSTRA),
                             vozes.TAXA_AMOSTRA, amostra, marca_ia=False)
            except ErroEstudio:
                continue  # fala pouco: fica com a voz padrão
            nome = f"Voz de {arquivo.stem}" + (f" ({quem})" if quem else "")
            saida[quem] = vozes.clonar(nome, amostra, True, alvo.codigo,
                                       descricao=f"Voz original do vídeo {arquivo.name}")
        if not nomes and saida[""] is padrao:
            raise ErroEstudio("Não há fala limpa suficiente no vídeo para clonar a voz.")
        return saida
    livres = [v for v in VOZES_ELENCO if v != padrao.id]
    for n, quem in enumerate(nomes):
        escolhida = (elenco or {}).get(quem)
        if escolhida:
            saida[quem] = vozes.obter(escolhida)
        elif n == 0:
            saida[quem] = padrao
        else:
            saida[quem] = vozes.obter(livres[(n - 1) % len(livres)])
    return saida


def dublar(arquivo: str | Path, destino: str = "pt-BR", voz: str = "", origem: str = "",
           voz_original: bool = False, consentimento: bool = False,
           volume_original: float = 0.12, legenda: str = "faixa", llm=None,
           projeto: str = "", legenda_pronta: str | Path | None = None, config=None,
           progresso=None, cancelado=None, saida: str | Path | None = None,
           separar_falantes: bool = False, elenco: dict[str, str] | None = None,
           fundo: str = "original") -> dict:
    """Dubla um vídeo ou áudio.

    - `legenda`: "faixa", "queimada" ou "nenhuma".
    - `separar_falantes`: descobre quem fala (diarização) e dá uma voz para cada pessoa; com
      `voz_original`, clona cada pessoa separadamente. `elenco` escolhe a voz de cada uma
      ({"Pessoa 1": "Mordomo"}).
    - `fundo`: "original" (o áudio original baixinho por baixo, `volume_original`), "musica"
      (tira a voz original e mantém música e efeitos, precisa do Demucs) ou "nenhum".
    """
    arquivo = Path(arquivo)
    if not arquivo.exists():
        raise ErroEstudio(f"Arquivo não encontrado: {arquivo}")
    alvo = idiomas.idioma(destino)
    pasta = _pasta_trabalho(arquivo)
    duracao = audio.duracao(arquivo)
    p = progresso or _nada

    if legenda_pronta:
        trechos = legendas.ler_arquivo(legenda_pronta)
        if not trechos:
            raise ErroEstudio("A legenda indicada está vazia.")
        originais = trechos
    else:
        originais, falado = _obter_trechos(arquivo, origem, config, _etapa(p, 0, 0.3),
                                           cancelado, pasta, separar_falantes)
        trechos = _traduzidos(originais, falado, alvo, llm, projeto, True,
                              _etapa(p, 0.3, 0.45), cancelado, pasta)

    perfis = _montar_elenco(trechos, originais, voz, elenco, voz_original, consentimento,
                            arquivo, alvo, pasta, p)
    faixa, ajustes = _faixa_dublada(trechos, perfis, alvo, duracao, pasta, config,
                                    _etapa(p, 0.47, 0.88), cancelado)

    volume = volume_original
    if fundo == "musica":
        import numpy as np

        from optimus.estudio import isolar

        p(0.89, "Separando a música e os efeitos do vídeo…")
        instrumental = audio.carregar(isolar.separar(arquivo)["fundo"], TAXA)
        n = max(len(instrumental), len(faixa))
        junto = np.zeros(n, dtype="float32")
        junto[:len(instrumental)] += instrumental
        junto[:len(faixa)] += faixa
        faixa, volume = np.clip(junto, -1, 1), 0.0
    elif fundo == "nenhum":
        volume = 0.0

    destino_dir = Path(saida) if saida else pasta_saidas(config)
    base = f"{arquivo.stem}.dublado.{alvo.codigo}"
    srt = legendas.salvar([Trecho(t.inicio, t.fim, legendas.quebrar_linhas(t.texto), t.falante)
                           for t in trechos], destino_dir / f"{base}.srt")
    usadas = list(dict.fromkeys((perfis.get(t.falante) or perfis[""]).nome for t in trechos))
    resultado = {"idioma": alvo.nome, "voz": ", ".join(usadas),
                 "trechos": len(trechos), "acelerados": len(ajustes), "legenda": str(srt)}
    if any(t.falante for t in trechos):
        resultado["elenco"] = {k: v.nome for k, v in perfis.items() if k}
    p(0.92, "Juntando tudo…")
    if audio.eh_video(arquivo):
        faixa_wav = pasta / f"faixa-{alvo.codigo}.wav"
        audio.salvar(faixa, TAXA, faixa_wav)  # com a marca d'água: é ela que vai no vídeo
        video = destino_dir / f"{base}{arquivo.suffix}"
        audio.juntar_video(arquivo, video, voz=faixa_wav, volume_original=volume,
                           legenda=None if legenda == "nenhuma" else srt,
                           queimar=legenda == "queimada", estilo=audio.estilo_legenda())
        resultado["video"] = str(video)
        resultado["audio"] = str(audio.salvar(faixa, TAXA, destino_dir / f"{base}.mp3"))
    else:
        import numpy as np

        mistura = faixa
        if volume > 0:
            original = audio.carregar(arquivo, TAXA)
            n = max(len(original), len(faixa))
            mistura = np.zeros(n, dtype="float32")
            mistura[:len(original)] += original * volume
            mistura[:len(faixa)] += faixa
            mistura = np.clip(mistura, -1, 1)
        resultado["audio"] = str(audio.salvar(mistura, TAXA, destino_dir / f"{base}.mp3"))
    registrar("dublagem", resultado.get("video") or resultado["audio"], voz=resultado["voz"],
              idioma=alvo.codigo)
    if ajustes:
        resultado["aviso"] = (f"{len(ajustes)} trecho(s) foram acelerados para caber no tempo. "
                              "Se ficou rápido, revise a legenda e duble de novo com "
                              "legenda_pronta.")
    return resultado


def dublar_lote(arquivos: list[str], destinos: list[str], **opcoes) -> list[dict]:
    """Vários vídeos em vários idiomas, um depois do outro."""
    progresso = opcoes.pop("progresso", None)
    cancelado = opcoes.pop("cancelado", None)
    total = max(1, len(arquivos) * len(destinos))
    saida, feito = [], 0
    for arq in arquivos:
        for dest in destinos:
            if cancelado and cancelado():
                return saida
            try:
                r = dublar(arq, dest, progresso=_etapa(progresso, feito / total,
                                                        (feito + 1) / total),
                           cancelado=cancelado, **opcoes)
                saida.append({"arquivo": arq, "idioma": dest, **r})
            except ErroEstudio as erro:
                saida.append({"arquivo": arq, "idioma": dest, "erro": str(erro)})
            feito += 1
    return saida
