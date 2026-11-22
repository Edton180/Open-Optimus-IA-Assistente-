"""Ferramentas do estúdio de voz: o Optimus gera, clona, legenda, traduz e dubla por pedido.

Ex.: "narra este texto com a voz Mordomo", "clona minha voz com o áudio gravacao.m4a",
"legenda esse vídeo em inglês", "dubla o video.mp4 para português com a minha voz".
Tarefas longas (dublagem, legendas) vão para a fila; "como está a dublagem?" mostra o progresso.
"""

from __future__ import annotations

import time
from pathlib import Path

from optimus.safety import CRITICO, LIVRE, MODERADO, Avaliacao
from optimus.tools.base import ferramenta, numero, resolver, texto

_BOOL = {"type": "boolean"}


def _erro(erro: Exception) -> dict:
    return {"erro": str(erro)}


def _arquivo(ctx, caminho: str) -> Path:
    alvo = resolver(ctx, caminho)
    if not alvo.exists():
        from optimus.estudio.audio import ErroEstudio

        raise ErroEstudio(f"Arquivo não encontrado: {alvo}")
    return alvo


def _config(ctx):
    return getattr(ctx, "config", None)


# ---------------------------------------------------------------------- vozes
@ferramenta(
    "estudio_vozes",
    "Lista as vozes do estúdio (prontas, clonadas e criadas) para narração e dublagem.",
    {}, grupo="estudio", risco=LIVRE,
)
def estudio_vozes(ctx):
    from optimus.estudio import motores, vozes

    return {"vozes": [{"nome": p.nome, "tipo": p.tipo, "genero": p.genero,
                       "descricao": p.descricao} for p in vozes.listar()],
            "clonagem_instalada": motores.clonagem_instalada()}


@ferramenta(
    "estudio_falar",
    "Gera um arquivo de áudio (narração, locução) com uma voz do estúdio, em português do "
    "Brasil ou outro idioma. Para vídeos, podcasts, avisos.",
    {"texto": texto("O texto a narrar"),
     "voz": texto("Nome da voz (padrão Valkyrie). Ex.: Mordomo, Nexus, minha voz"),
     "idioma": texto("Idioma da fala (padrão português do Brasil)"),
     "velocidade": numero("Ritmo: 0.7 a 1.5 (padrão 1)"),
     "arquivo": texto("Onde salvar (padrão: pasta de saídas do estúdio), .mp3 .wav .flac")},
    grupo="estudio", risco=LIVRE, obrigatorios=["texto"],
)
def estudio_falar(ctx, texto: str, voz: str = "", idioma: str = "", velocidade: float = 1.0,
                  arquivo: str = ""):
    from optimus.estudio import audio, motores, pasta_saidas, registrar, vozes
    from optimus.estudio.audio import ErroEstudio

    try:
        perfil = vozes.obter(voz)
        x = motores.gerar(texto, perfil, idioma, float(velocidade or 1.0), _config(ctx))
        destino = resolver(ctx, arquivo) if arquivo else \
            pasta_saidas(_config(ctx)) / f"narracao-{time.strftime('%Y%m%d-%H%M%S')}.mp3"
        salvo = audio.salvar(x, motores.TAXA, destino, titulo=texto[:60])
        registrar("narracao", salvo, texto, perfil.nome, idioma or perfil.idioma)
        return {"arquivo": str(salvo), "voz": perfil.nome,
                "segundos": round(len(x) / motores.TAXA, 1),
                "mensagem": f"Pronto: {salvo.name} com a voz {perfil.nome}."}
    except ErroEstudio as erro:
        return _erro(erro)


@ferramenta(
    "estudio_clonar_voz",
    "Clona uma voz a partir de uma gravação (10 a 30 s de fala limpa, sem música). Só com "
    "consentimento: a voz precisa ser da pessoa que pede ou ela precisa ter autorização.",
    {"nome": texto("Nome da nova voz, ex.: Minha voz"),
     "arquivo": texto("Áudio ou vídeo com a voz"),
     "consentimento": {**_BOOL, "description": "A pessoa confirmou que a voz é dela ou que "
                                               "tem autorização"},
     "inicio": numero("Segundo onde a fala começa (opcional)"),
     "fim": numero("Segundo onde a fala termina (opcional)"),
     "genero": {"type": "string", "enum": ["feminina", "masculina"]}},
    grupo="estudio", obrigatorios=["nome", "arquivo", "consentimento"],
    risco=lambda a, c: Avaliacao(CRITICO, f"clonar a voz da gravação {a.get('arquivo')}: "
                                          "confirme que a voz é sua ou que você tem "
                                          "autorização da pessoa"),
)
def estudio_clonar_voz(ctx, nome: str, arquivo: str, consentimento: bool = False,
                       inicio: float = 0, fim: float = 0, genero: str = ""):
    from optimus.estudio import motores, vozes
    from optimus.estudio.audio import ErroEstudio

    try:
        p = vozes.clonar(nome, _arquivo(ctx, arquivo), bool(consentimento), "pt-BR", genero,
                         inicio=float(inicio or 0), fim=float(fim or 0))
        aviso = "" if motores.clonagem_instalada() else \
            " Para usar, instale o motor de clonagem: pip install chatterbox-tts."
        return {"voz": p.nome, "mensagem": f"Voz '{p.nome}' clonada.{aviso}"}
    except ErroEstudio as erro:
        return _erro(erro)


@ferramenta(
    "estudio_criar_voz",
    "Cria uma voz nova a partir de uma descrição, ex.: 'masculina grave e calma', 'feminina "
    "jovem e animada', 'robótica', 'sussurro'. Pode partir de outra voz (base).",
    {"nome": texto("Nome da voz"), "descricao": texto("Como a voz deve soar"),
     "base": texto("Voz de partida (opcional), inclusive uma clonada")},
    grupo="estudio", risco=LIVRE, obrigatorios=["nome", "descricao"],
)
def estudio_criar_voz(ctx, nome: str, descricao: str, base: str = ""):
    from optimus.estudio import vozes
    from optimus.estudio.audio import ErroEstudio

    try:
        p = vozes.criar(nome, descricao, base=base)
        return {"voz": p.nome, "tom": p.tom, "velocidade": p.velocidade, "efeito": p.efeito,
                "mensagem": f"Criei a voz '{p.nome}'. Peça uma amostra para ouvir."}
    except ErroEstudio as erro:
        return _erro(erro)


@ferramenta(
    "estudio_ajustar_voz",
    "Ajusta uma voz: tom (-6 grave a +6 agudo), velocidade, expressividade (0 a 1), efeito.",
    {"voz": texto("Nome da voz"), "tom": numero("Semitons"), "velocidade": numero("0.7 a 1.5"),
     "expressividade": numero("0 neutra a 1 dramática"),
     "efeito": {"type": "string", "enum": ["", "cyber", "sussurro"]}},
    grupo="estudio", risco=LIVRE, obrigatorios=["voz"],
)
def estudio_ajustar_voz(ctx, voz: str, tom: float | None = None, velocidade: float | None = None,
                        expressividade: float | None = None, efeito: str | None = None):
    from optimus.estudio import vozes
    from optimus.estudio.audio import ErroEstudio

    try:
        p = vozes.editar(voz, tom=tom, velocidade=velocidade, expressividade=expressividade,
                         efeito=efeito)
        return {"voz": p.nome, "mensagem": f"Voz '{p.nome}' ajustada."}
    except ErroEstudio as erro:
        return _erro(erro)


@ferramenta(
    "estudio_apagar_voz", "Apaga uma voz clonada ou criada.",
    {"voz": texto("Nome da voz")}, grupo="estudio", risco=MODERADO,
)
def estudio_apagar_voz(ctx, voz: str):
    from optimus.estudio import vozes
    from optimus.estudio.audio import ErroEstudio

    try:
        return {"mensagem": f"Apaguei a voz '{vozes.apagar(voz).nome}'."}
    except ErroEstudio as erro:
        return _erro(erro)


@ferramenta(
    "estudio_converter_voz",
    "Troca a voz de uma gravação por outra voz (voz para voz), mantendo a fala e o ritmo.",
    {"arquivo": texto("Gravação de entrada"), "voz": texto("Voz de destino")},
    grupo="estudio", risco=LIVRE, obrigatorios=["arquivo", "voz"],
)
def estudio_converter_voz(ctx, arquivo: str, voz: str):
    from optimus.estudio import audio, motores, pasta_saidas, registrar
    from optimus.estudio.audio import ErroEstudio

    try:
        entrada = _arquivo(ctx, arquivo)
        x = motores.converter(entrada, voz, _config(ctx))
        destino = pasta_saidas(_config(ctx)) / f"{entrada.stem}.voz-{voz.lower()}.mp3"
        salvo = audio.salvar(x, motores.TAXA, destino)
        registrar("conversao", salvo, voz=voz)
        return {"arquivo": str(salvo), "mensagem": f"Convertido para a voz {voz}."}
    except ErroEstudio as erro:
        return _erro(erro)


# ---------------------------------------------------------------------- transcrição e legendas
@ferramenta(
    "estudio_transcrever",
    "Transcreve um áudio ou vídeo para texto (TXT) ou legenda com tempo (SRT/VTT), offline.",
    {"arquivo": texto("Áudio ou vídeo"),
     "idioma": texto("Idioma falado (vazio = detectar)"),
     "formato": {"type": "string", "enum": ["txt", "srt", "vtt"]}},
    grupo="estudio", risco=LIVRE, obrigatorios=["arquivo"],
)
def estudio_transcrever(ctx, arquivo: str, idioma: str = "", formato: str = "txt"):
    from optimus.estudio import legendas, pasta_saidas, registrar, transcrever
    from optimus.estudio.audio import ErroEstudio

    try:
        entrada = _arquivo(ctx, arquivo)
        trechos, falado = transcrever.transcrever(entrada, idioma, config=_config(ctx))
        destino = pasta_saidas(_config(ctx)) / f"{entrada.stem}.{formato or 'txt'}"
        legendas.salvar(trechos, destino)
        registrar("transcricao", destino, idioma=falado.codigo)
        return {"arquivo": str(destino), "idioma": falado.nome, "trechos": len(trechos),
                "previa": legendas.para_txt(trechos)[:1500]}
    except ErroEstudio as erro:
        return _erro(erro)


@ferramenta(
    "estudio_traduzir_legenda",
    "Traduz um arquivo de legenda (SRT/VTT) para outro idioma mantendo os tempos. Usa o "
    "glossário do projeto (termos que não devem ser traduzidos).",
    {"arquivo": texto("Legenda .srt ou .vtt"), "idioma": texto("Idioma de destino"),
     "projeto": texto("Glossário a usar (opcional)")},
    grupo="estudio", risco=LIVRE, obrigatorios=["arquivo", "idioma"],
)
def estudio_traduzir_legenda(ctx, arquivo: str, idioma: str, projeto: str = ""):
    from optimus.estudio import idiomas, legendas, registrar, traduzir
    from optimus.estudio.audio import ErroEstudio

    try:
        entrada = _arquivo(ctx, arquivo)
        alvo = idiomas.idioma(idioma)
        trechos = traduzir.traduzir(legendas.ler_arquivo(entrada), alvo.codigo,
                                    traduzir.llm_do_contexto(ctx), projeto=projeto)
        destino = entrada.with_name(f"{entrada.stem}.{alvo.codigo}{entrada.suffix}")
        legendas.salvar(trechos, destino)
        registrar("traducao", destino, idioma=alvo.codigo)
        return {"arquivo": str(destino), "idioma": alvo.nome, "trechos": len(trechos)}
    except (ErroEstudio, ValueError) as erro:
        return _erro(erro)


def _na_fila(ctx, tipo: str, titulo: str, trabalho, **args) -> dict:
    from optimus.estudio.fila import fila

    t = fila().adicionar(tipo, titulo, trabalho, **args)
    return {"tarefa": t.id, "mensagem": f"Comecei: {titulo}. Pode continuar usando o Optimus; "
                                        "pergunte 'como está a tarefa?' para ver o progresso."}


@ferramenta(
    "estudio_legendar",
    "Cria legenda para um vídeo ou áudio (no idioma falado ou traduzida) e, se pedir, põe no "
    "vídeo: queimada na imagem ou como faixa que liga e desliga. Roda em segundo plano.",
    {"arquivo": texto("Vídeo ou áudio"),
     "idioma": texto("Idioma da legenda (vazio = o mesmo da fala)"),
     "no_video": {"type": "string", "enum": ["nao", "faixa", "queimada"],
                  "description": "Colocar no vídeo (padrão: só gerar o arquivo .srt)"},
     "projeto": texto("Glossário a usar (opcional)")},
    grupo="estudio", risco=MODERADO, obrigatorios=["arquivo"],
)
def estudio_legendar(ctx, arquivo: str, idioma: str = "", no_video: str = "nao",
                     projeto: str = ""):
    from optimus.estudio import dublagem, idiomas, traduzir
    from optimus.estudio.audio import ErroEstudio

    try:
        entrada = _arquivo(ctx, arquivo)
        if idioma:
            idiomas.idioma(idioma)  # valida antes de ir para a fila
        llm = traduzir.llm_do_contexto(ctx) if idioma else None
    except (ErroEstudio, ValueError) as erro:
        return _erro(erro)

    def trabalho(progresso, cancelado, **_):
        return dublagem.legendar(entrada, idioma, queimar=no_video == "queimada",
                                 embutir=no_video == "faixa", llm=llm, projeto=projeto,
                                 config=_config(ctx), progresso=progresso, cancelado=cancelado)

    return _na_fila(ctx, "legenda", f"legendar {entrada.name}", trabalho, arquivo=str(entrada),
                    idioma=idioma)


@ferramenta(
    "estudio_dublar",
    "Dubla um vídeo ou áudio para outro idioma (padrão português do Brasil): transcreve, "
    "traduz, fala com a voz escolhida e sincroniza. voz_original=true clona a voz de quem "
    "fala no vídeo (só com consentimento). Roda em segundo plano.",
    {"arquivo": texto("Vídeo ou áudio"),
     "idioma": texto("Idioma da dublagem (padrão português do Brasil)"),
     "voz": texto("Voz a usar (padrão Valkyrie)"),
     "voz_original": {**_BOOL, "description": "Usar a voz de quem fala no vídeo (clonagem)"},
     "consentimento": {**_BOOL, "description": "Confirmou que a voz é dele ou tem "
                                               "autorização (só para voz_original)"},
     "legenda": {"type": "string", "enum": ["faixa", "queimada", "nenhuma"]},
     "volume_original": numero("Volume do áudio original por baixo, 0 a 1 (padrão 0.12)"),
     "legenda_pronta": texto("Legenda revisada para dublar a partir dela (opcional)"),
     "projeto": texto("Glossário a usar (opcional)")},
    grupo="estudio", obrigatorios=["arquivo"],
    risco=lambda a, c: Avaliacao(CRITICO if a.get("voz_original") else MODERADO,
                                 f"dublar {a.get('arquivo')}"
                                 + (" clonando a voz de quem fala" if a.get("voz_original")
                                    else "")),
)
def estudio_dublar(ctx, arquivo: str, idioma: str = "pt-BR", voz: str = "",
                   voz_original: bool = False, consentimento: bool = False,
                   legenda: str = "faixa", volume_original: float = 0.12,
                   legenda_pronta: str = "", projeto: str = ""):
    from optimus.estudio import dublagem, idiomas, traduzir, vozes
    from optimus.estudio.audio import ErroEstudio

    try:
        entrada = _arquivo(ctx, arquivo)
        alvo = idiomas.idioma(idioma or "pt-BR")
        if voz and not voz_original:
            vozes.obter(voz)
        if voz_original and not consentimento:
            return {"erro": "Para usar a voz de quem fala no vídeo, a pessoa precisa confirmar "
                            "que é a voz dela ou que tem autorização."}
        pronta = str(_arquivo(ctx, legenda_pronta)) if legenda_pronta else None
        llm = None if pronta else traduzir.llm_do_contexto(ctx)
    except (ErroEstudio, ValueError) as erro:
        return _erro(erro)

    def trabalho(progresso, cancelado, **_):
        return dublagem.dublar(entrada, alvo.codigo, voz, voz_original=bool(voz_original),
                               consentimento=bool(consentimento),
                               volume_original=float(volume_original or 0), legenda=legenda,
                               llm=llm, projeto=projeto, legenda_pronta=pronta,
                               config=_config(ctx), progresso=progresso, cancelado=cancelado)

    return _na_fila(ctx, "dublagem", f"dublar {entrada.name} para {alvo.nome}", trabalho,
                    arquivo=str(entrada), idioma=alvo.codigo, voz=voz)


@ferramenta(
    "estudio_tarefas",
    "Mostra o andamento das tarefas do estúdio (dublagens, legendas) e onde ficaram os "
    "arquivos prontos.",
    {}, grupo="estudio", risco=LIVRE,
)
def estudio_tarefas(ctx):
    from optimus.estudio.fila import fila

    return {"tarefas": [{"id": t.id, "titulo": t.titulo, "estado": t.estado,
                         "progresso": f"{int(t.progresso * 100)}%", "mensagem": t.mensagem,
                         "resultado": t.resultado, "erro": t.erro}
                        for t in fila().listar(10)]}


@ferramenta(
    "estudio_cancelar", "Cancela uma tarefa do estúdio (a última, se não disser qual).",
    {"tarefa": texto("Id da tarefa (opcional)")}, grupo="estudio", risco=LIVRE,
    obrigatorios=[],
)
def estudio_cancelar(ctx, tarefa: str = ""):
    from optimus.estudio.fila import fila

    f = fila()
    alvo = tarefa or next((t.id for t in f.listar() if not t.terminou), "")
    if not alvo or not f.cancelar(alvo):
        return {"erro": "Não há tarefa rodando para cancelar."}
    return {"mensagem": "Cancelado."}


# ---------------------------------------------------------------------- pronúncia e glossário
@ferramenta(
    "pronuncia_adicionar",
    "Ensina a pronúncia de uma palavra para todas as vozes (ex.: 'Kaik' se fala 'Káique').",
    {"escrito": texto("Como se escreve"), "falado": texto("Como se fala")},
    grupo="estudio", risco=LIVRE,
)
def pronuncia_adicionar(ctx, escrito: str, falado: str):
    from optimus.estudio import pronuncia

    try:
        pronuncia.adicionar(escrito, falado)
    except ValueError as erro:
        return _erro(erro)
    return {"mensagem": f"Combinado: '{escrito}' vai soar como '{falado}'."}


@ferramenta(
    "pronuncia_listar", "Lista o dicionário de pronúncia.", {}, grupo="estudio", risco=LIVRE,
)
def pronuncia_listar(ctx):
    from optimus.estudio import pronuncia

    return {"regras": pronuncia.listar()}


@ferramenta(
    "pronuncia_remover", "Remove uma palavra do dicionário de pronúncia.",
    {"escrito": texto("A palavra")}, grupo="estudio", risco=LIVRE,
)
def pronuncia_remover(ctx, escrito: str):
    from optimus.estudio import pronuncia

    return {"mensagem": "Removido." if pronuncia.remover(escrito) else "Não estava lá."}


@ferramenta(
    "glossario_adicionar",
    "Adiciona termos que não devem ser traduzidos (nomes, marcas) ou traduções fixas ao "
    "glossário de um projeto de legendas e dublagem.",
    {"projeto": texto("Nome do projeto (padrão: geral)"),
     "manter": texto("Termos a manter, separados por vírgula"),
     "traducoes": texto("Traduções fixas: 'deploy=implantação; bug=erro'")},
    grupo="estudio", risco=LIVRE, obrigatorios=[],
)
def glossario_adicionar(ctx, projeto: str = "geral", manter: str = "", traducoes: str = ""):
    from optimus.estudio import traduzir

    fixas = {}
    for par in traducoes.split(";"):
        if "=" in par:
            a, b = par.split("=", 1)
            fixas[a.strip()] = b.strip()
    gl = traduzir.salvar_glossario(projeto or "geral",
                                   [m.strip() for m in manter.split(",") if m.strip()], fixas)
    return {"glossario": gl}
