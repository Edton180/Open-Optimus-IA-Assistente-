"""Comando `optimus estudio`: o estúdio de voz pelo terminal."""

from __future__ import annotations

import argparse
import shutil
import sys


def _instalado(modulo: str) -> bool:
    try:
        from optimus.pacotes import modulo_instalado

        return modulo_instalado(modulo)
    except (ImportError, ValueError):
        return False


def diagnostico() -> list[tuple[str, bool, str]]:
    from optimus.estudio import audio, motores
    from optimus.pacotes import comando_pip
    from optimus.voice import tts

    try:
        audio.ffmpeg()
        tem_ffmpeg = True
    except audio.ErroEstudio:
        tem_ffmpeg = False
    return [
        ("ffmpeg (áudio e vídeo)", tem_ffmpeg, comando_pip("imageio-ffmpeg")),
        ("Transcrição (faster-whisper)", _instalado("faster_whisper"),
         comando_pip("faster-whisper")),
        ("Transcrição reserva e quem fala quando (sherpa-onnx)", _instalado("sherpa_onnx"),
         comando_pip("sherpa-onnx<2")),
        ("Separar voz da música (Demucs)", _instalado("demucs"), comando_pip("demucs")),
        ("Audiolivro a partir de PDF (pypdf)", _instalado("pypdf"), comando_pip("pypdf")),
        ("Vozes offline pt-BR (Kokoro)", tts.kokoro_instalado(), "optimus voz-diagnostico"),
        ("Vozes online em 18 idiomas (Edge)", tts.edge_instalado(), comando_pip("edge-tts")),
        ("Clonagem, criar voz e 600+ idiomas (OmniVoice)", _instalado("omnivoice"),
         comando_pip("omnivoice")),
        ("Clonagem em 23 idiomas e conversor de voz (Chatterbox)",
         motores.chatterbox_instalado(), comando_pip("chatterbox-tts")),
        ("Vozes Piper offline (sherpa-onnx < 2)", _instalado("sherpa_onnx"),
         comando_pip("sherpa-onnx<2")),
        ("Placa de vídeo", motores.dispositivo() != "cpu" or bool(shutil.which("nvidia-smi")),
         "opcional: deixa clonagem e transcrição bem mais rápidas"),
    ]


def _progresso(valor: float, mensagem: str = "") -> None:
    sys.stdout.write(f"\r{int(valor * 100):3d}%  {mensagem[:70]:70}")
    sys.stdout.flush()


def _imprimir(r: dict) -> int:
    if r.get("erro"):
        print(f"\n⚠️  {r['erro']}")
        return 1
    print()
    for chave, valor in r.items():
        if isinstance(valor, list):
            valor = "\n    " + "\n    ".join(str(v) for v in valor)
        print(f"  {chave}: {valor}")
    return 0


def _pares(texto: str) -> dict[str, str]:
    from optimus.tools.estudio import _pares as pares

    return pares(texto)


def executar(args, criar_optimus) -> int:
    from optimus.estudio import (
        audio,
        audiolivro,
        diarizar,
        dublagem,
        historia,
        isolar,
        legendas,
        marca,
        motores,
        pasta_saidas,
        pronuncia,
        traduzir,
        transcrever,
        vozes,
    )
    from optimus.estudio.audio import ErroEstudio

    acao = args.acao
    try:
        if acao == "diagnostico":
            for nome, ok, dica in diagnostico():
                print(f"  {'✅' if ok else '❌'} {nome}" + ("" if ok else f"  → {dica}"))
            return 0
        if acao == "vozes":
            for p in vozes.listar():
                print(f"  {p.nome:24} {p.tipo:8} {p.genero:9} {p.descricao}")
            return 0
        if acao == "modelos":
            return _modelos(args)
        if acao == "receitas":
            from optimus.estudio import automacao

            for r in automacao.receitas():
                opcoes = "; ".join(f"{k}={v}" for k, v in r.opcoes.items())
                print(f"  {r.nome:32} {r.acao:24} {opcoes}")
            for d in automacao.observadas():
                print(f"  📂 {d['pasta']} → {d['receita']}")
            return 0
        if acao == "desempenho":
            from optimus import config as cfg
            from optimus.estudio import desempenho

            config = cfg.carregar()
            if args.itens:
                desempenho.escolher(config, args.itens[0])
            atual = desempenho.atual(config)
            print(f"  Atual: {atual.descricao} (transcrição {atual.transcricao}, "
                  f"{atual.passos} passos). Recomendada aqui: {desempenho.recomendar()}")
            return 0
        if acao == "observar":
            return _observar(args)
        if acao == "pronuncia":
            if len(args.itens) >= 2:
                pronuncia.adicionar(args.itens[0], " ".join(args.itens[1:]))
            for r in pronuncia.listar():
                print(f"  {r['escrito']} → {r['falado']}")
            return 0
        if not args.itens:
            print("Faltou o texto ou o arquivo. Veja: optimus estudio --help")
            return 1
        optimus = criar_optimus(args)
        config = optimus.config
        llm = traduzir.llm_do_optimus(optimus.motor, optimus.modelo_atual())
        if acao == "falar":
            x = motores.gerar(" ".join(args.itens), args.voz, args.idioma, args.velocidade,
                              config)
            destino = args.saida or str(pasta_saidas(config) / "narracao.mp3")
            print(f"Salvo em {audio.salvar(x, motores.TAXA, destino)}")
            return 0
        if acao == "clonar":
            nome, arquivo = (args.itens + [""])[:2]
            if not args.consentimento:
                print("Use --consentimento para declarar: " + vozes.DECLARACAO)
                return 1
            p = vozes.clonar(nome, arquivo, True, args.idioma or "pt-BR")
            print(f"Voz '{p.nome}' clonada.")
            return 0
        if acao == "criar-voz":
            p = vozes.criar(args.itens[0], " ".join(args.itens[1:]), base=args.voz)
            print(f"Voz '{p.nome}' criada (tom {p.tom:+}, ritmo {p.velocidade}, "
                  f"efeito {p.efeito or 'nenhum'}).")
            return 0
        if acao == "transcrever":
            trechos, falado = transcrever.transcrever(args.itens[0], args.idioma, config=config,
                                                      progresso=_progresso)
            destino = args.saida or str(pasta_saidas(config) / f"transcricao.{args.formato}")
            print(f"\nIdioma: {falado.nome}. Salvo em {legendas.salvar(trechos, destino)}")
            return 0
        if acao == "traduzir":
            entrada = args.itens[0]
            trechos = traduzir.traduzir(legendas.ler_arquivo(entrada), args.idioma or "pt-BR",
                                        llm, projeto=args.projeto, progresso=_progresso)
            destino = args.saida or entrada.rsplit(".", 1)[0] + f".{args.idioma or 'pt-BR'}.srt"
            print(f"\nSalvo em {legendas.salvar(trechos, destino)}")
            return 0
        if acao == "legendar":
            return _imprimir(dublagem.legendar(
                args.itens[0], args.idioma, queimar=args.legenda == "queimada",
                embutir=args.legenda == "faixa", llm=llm, projeto=args.projeto, config=config,
                progresso=_progresso, saida=args.saida, falantes=args.falantes))
        if acao == "dublar":
            elenco = _pares(args.elenco)
            return _imprimir(dublagem.dublar(
                args.itens[0], args.idioma or "pt-BR", args.voz, voz_original=args.voz_original,
                consentimento=args.consentimento, volume_original=args.volume_original,
                legenda=args.legenda or "faixa", llm=llm, projeto=args.projeto,
                legenda_pronta=args.legenda_pronta, config=config, progresso=_progresso,
                saida=args.saida, separar_falantes=args.falantes or bool(elenco),
                elenco=elenco or None, fundo=args.fundo))
        if acao == "audiolivro":
            return _imprimir(audiolivro.gerar(
                args.itens[0], args.voz, args.idioma, args.titulo, args.autor, args.capa,
                velocidade=args.velocidade, config=config, progresso=_progresso,
                saida=args.saida or None))
        if acao == "historia":
            return _imprimir(historia.gerar(
                args.itens[0] if len(args.itens) == 1 else "\n".join(args.itens),
                _pares(args.elenco), args.voz, args.idioma, args.titulo, config=config,
                progresso=_progresso, saida=args.saida or None))
        if acao == "separar":
            partes = isolar.separar(args.itens[0], _progresso)
            return _imprimir({k: str(v) for k, v in partes.items()})
        if acao == "quem-fala":
            for t in diarizar.falantes(args.itens[0], args.pessoas, progresso=_progresso):
                print(f"\n  {t.inicio:8.1f}s → {t.fim:8.1f}s  {t.falante}", end="")
            print()
            return 0
        if acao == "verificar-ia":
            return _imprimir(marca.detectar(args.itens[0]))
        if acao == "receita":
            from optimus.estudio import automacao

            if len(args.itens) < 2:
                print("Use: optimus estudio receita \"Nome da receita\" arquivo")
                return 1
            return _imprimir(automacao.aplicar(args.itens[0], args.itens[1], config))
        if acao == "converter":
            x = motores.converter(args.itens[0], args.voz, config)
            destino = args.saida or str(pasta_saidas(config) / "convertido.mp3")
            print(f"Salvo em {audio.salvar(x, motores.TAXA, destino)}")
            return 0
    except (ErroEstudio, ValueError, OSError) as erro:
        print(f"\n⚠️  {erro}")
        return 1
    print(f"Ação desconhecida: {acao}")
    return 1


def _modelos(args) -> int:
    from optimus.estudio import modelos

    if len(args.itens) >= 2 and args.itens[0] in ("instalar", "baixar", "remover"):
        for ident in args.itens[1:]:
            if args.itens[0] == "remover":
                modelos.remover(ident)
                print(f"  Removido: {ident}")
            else:
                modelos.instalar(ident, _progresso)
                print(f"\n  Instalado: {ident}")
        return 0
    for m in modelos.listar():
        estado = "✅" if m["instalado"] else "  "
        print(f"  {estado} {m['id']:30} {m['tipo']:12} {m['licenca']:16} ~{m['tamanho_mb']} MB"
              f"  {m['descricao']}")
    print("\n  Instalar: optimus estudio modelos instalar ID   Remover: ... remover ID")
    return 0


def _observar(args) -> int:
    import time

    from optimus import config as cfg
    from optimus.estudio import automacao

    if len(args.itens) >= 2:
        regra = automacao.observar(args.itens[0], " ".join(args.itens[1:]))
        print(f"  Observando {regra['pasta']} com a receita '{regra['receita']}'.")
    if not automacao.observadas():
        print("  Nenhuma pasta observada. Use: optimus estudio observar PASTA \"Receita\"")
        return 1
    for d in automacao.observadas():
        print(f"  📂 {d['pasta']} → {d['receita']}")
    print("  Esperando arquivos novos (Ctrl+C para sair)…")
    obs = automacao.Observador(cfg.carregar(), ao_processar=lambda item: print(
        f"  ✔ {item['arquivo']}: {item['resultado']}"))
    try:
        while True:
            obs.uma_vez()
            time.sleep(obs.intervalo)
    except KeyboardInterrupt:
        return 0


def registrar(sub, funcao) -> None:
    p = sub.add_parser("estudio", help="estúdio de voz: narrar, clonar, legendar, traduzir, dublar",
                       formatter_class=argparse.RawDescriptionHelpFormatter,
                       description="""Exemplos:
  optimus estudio diagnostico
  optimus estudio falar "Olá, pessoal!" --voz Mordomo --saida ola.mp3
  optimus estudio clonar "Minha voz" gravacao.m4a --consentimento
  optimus estudio criar-voz Narradora feminina calma e grave
  optimus estudio transcrever aula.mp4 --formato srt
  optimus estudio legendar video.mp4 --idioma en-US --legenda queimada
  optimus estudio dublar video.mp4 --idioma pt-BR --voz "Minha voz"
  optimus estudio dublar entrevista.mp4 --voz-original --consentimento
  optimus estudio dublar podcast.mp4 --falantes --fundo musica
  optimus estudio dublar podcast.mp4 --elenco "Pessoa 1=Nexus; Pessoa 2=Aurora"
  optimus estudio audiolivro livro.epub --voz Mordomo --autor "Fulano" --capa capa.jpg
  optimus estudio historia roteiro.txt --elenco "Ana=Valkyrie; Bruno=Nexus"
  optimus estudio separar musica.mp3
  optimus estudio quem-fala entrevista.mp4
  optimus estudio verificar-ia audio.mp3
  optimus estudio pronuncia Kaik Káique
  optimus estudio modelos                       (motores e modelos: instalar/remover)
  optimus estudio modelos instalar omnivoice piper-pt_BR-faber-medium
  optimus estudio desempenho qualidade          (auto, rapido, equilibrado, qualidade)
  optimus estudio receitas
  optimus estudio receita "Dublar para inglês" video.mp4
  optimus estudio observar ~/Videos/para-dublar "Dublar para português"
""")
    p.add_argument("acao", choices=["diagnostico", "vozes", "falar", "clonar", "criar-voz",
                                    "transcrever", "traduzir", "legendar", "dublar",
                                    "converter", "pronuncia", "audiolivro", "historia",
                                    "separar", "quem-fala", "verificar-ia", "modelos",
                                    "desempenho", "receitas", "receita", "observar"])
    p.add_argument("itens", nargs="*", help="texto, nome e/ou arquivo, conforme a ação")
    p.add_argument("--voz", default="", help="voz a usar (padrão Valkyrie)")
    p.add_argument("--idioma", default="", help="idioma (padrão português do Brasil)")
    p.add_argument("--velocidade", type=float, default=1.0)
    p.add_argument("--saida", default="", help="arquivo ou pasta de saída")
    p.add_argument("--formato", default="srt", choices=["srt", "vtt", "txt"])
    p.add_argument("--legenda", default="", choices=["", "faixa", "queimada", "nenhuma"])
    p.add_argument("--legenda-pronta", default=None, help="dublar a partir desta legenda")
    p.add_argument("--projeto", default="", help="glossário a usar")
    p.add_argument("--voz-original", action="store_true",
                   help="dublar com a voz de quem fala no vídeo (clonagem)")
    p.add_argument("--consentimento", action="store_true",
                   help="declaro que a voz é minha ou que tenho autorização")
    p.add_argument("--volume-original", type=float, default=0.12)
    p.add_argument("--falantes", action="store_true",
                   help="uma voz para cada pessoa (dublar) / nome de quem fala (legendar)")
    p.add_argument("--elenco", default="", help="voz de cada pessoa: 'Ana=Valkyrie; Bruno=Nexus'")
    p.add_argument("--fundo", default="original", choices=["original", "musica", "nenhum"],
                   help="o que fica por baixo da dublagem")
    p.add_argument("--pessoas", type=int, default=0, help="quantas pessoas falam (0 = descobrir)")
    p.add_argument("--titulo", default="")
    p.add_argument("--autor", default="")
    p.add_argument("--capa", default=None, help="imagem de capa do audiolivro")
    p.add_argument("--demo", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=funcao)
