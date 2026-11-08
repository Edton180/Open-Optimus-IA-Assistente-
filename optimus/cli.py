"""Linha de comando do Optimus.

    optimus                    conversa no terminal
    optimus gui                abre a interface visual no navegador
    optimus voz                conversa por voz (palavra de ativação "Optimus")
    optimus tarefa "objetivo"  modo autônomo: planeja e executa até concluir
    optimus hardware           mostra o perfil escolhido para este PC
    optimus instalar-modelo    baixa o modelo ideal para este PC (Ollama)
    optimus vozes              lista as vozes; --baixar instala as vozes offline
    optimus doutor             verifica se está tudo funcionando
    optimus config             mostra ou altera configurações (ex.: optimus config agente.modo seguro)
    optimus aprender FONTE     estuda um site, arquivo ou texto
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from optimus import __version__
from optimus import config as cfg

AVISO_LEGAL = ("O Optimus executa ações reais no seu computador. O uso é de inteira "
               "responsabilidade de quem o instala e opera. Veja o README.")


def _cores() -> bool:
    return sys.stdout.isatty()


def _c(texto: str, codigo: str) -> str:
    return f"\033[{codigo}m{texto}\033[0m" if _cores() else texto


def _confirmar_terminal(chamada, avaliacao) -> bool:
    from optimus.safety import interpretar_confirmacao

    cor = "91" if avaliacao.nivel >= 2 else "93"
    print(_c(f"\n⚠  O Optimus quer {avaliacao.motivo}", cor))
    print(_c(f"   {chamada.nome}({json.dumps(chamada.argumentos, ensure_ascii=False)})", "90"))
    dica = 'digite "confirmo"' if avaliacao.nivel >= 2 else 'digite "sim"'
    try:
        resposta = input(_c(f"   Autoriza? ({dica} para aprovar, qualquer outra coisa nega): ",
                            cor))
    except EOFError:
        return False
    return interpretar_confirmacao(resposta, avaliacao.nivel)


def _mostrar_evento(evento: dict) -> None:
    tipo = evento["tipo"]
    if tipo == "ferramenta":
        argumentos = json.dumps(evento["argumentos"], ensure_ascii=False)
        print(_c(f"  🔧 {evento['nome']} {argumentos[:100]} [{evento['nivel']}]", "90"))
    elif tipo == "aviso":
        print(_c(f"  ⚠ {evento['texto']}", "93"))


def _criar(args=None):
    from optimus.app import Optimus

    optimus = Optimus()
    if args is not None and getattr(args, "demo", False):
        from optimus.engine.demo import MotorDemo

        optimus.motor = MotorDemo()
    return optimus


def cmd_chat(args) -> int:
    optimus = _criar(args)
    agente = optimus.criar_agente(confirmar=_confirmar_terminal, ao_evento=_mostrar_evento)
    nome = optimus.config.get("geral", "nome")
    if not optimus.motor.disponivel():
        print(_c("O motor de IA não respondeu. Rode `optimus doutor` ou `optimus "
                 "instalar-modelo`. Usando o modo demonstração por enquanto.", "93"))
        from optimus.engine.demo import MotorDemo

        agente.motor = MotorDemo()
    print(_c(f"{nome} {__version__}", "96;1") + _c(f"  ·  modelo {optimus.modelo_atual()}  ·  "
                                                    f"perfil {optimus.perfil.nome}  ·  modo "
                                                    f"{agente.modo}", "90"))
    print(_c("Escreva e aperte Enter. /sair para sair, /nova para limpar a conversa.", "90"))
    optimus.iniciar_lembretes(lambda l: print(_c(f"\n⏰ Lembrete: {l['texto']}", "95")))
    historico: list[dict] = []
    while True:
        try:
            texto = input(_c("\nvocê › ", "94;1")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not texto:
            continue
        if texto in ("/sair", "/exit", "sair"):
            return 0
        if texto == "/nova":
            historico = []
            print(_c("Conversa nova.", "90"))
            continue
        resposta = agente.responder(texto, historico)
        historico += [{"role": "user", "content": texto},
                      {"role": "assistant", "content": resposta}]
        print(_c(f"{nome.lower()} › ", "96;1") + resposta)


def cmd_tarefa(args) -> int:
    optimus = _criar(args)
    optimus.config.definir("agente", "modo", "autonomo")
    agente = optimus.criar_agente(confirmar=_confirmar_terminal, ao_evento=_mostrar_evento)
    print(_c(f"Modo autônomo: {args.objetivo}", "95;1"))
    print(agente.responder(args.objetivo))
    return 0


def cmd_gui(args) -> int:
    from optimus.web.server import iniciar

    config = cfg.carregar()
    host = "0.0.0.0" if args.rede else config.get("web", "host", "127.0.0.1")
    optimus = _criar(args)
    iniciar(host=host, porta=args.porta or config.get("web", "porta", 8765),
            abrir_navegador=not args.sem_navegador, optimus=optimus)
    return 0


def cmd_voz(args) -> int:
    from optimus.voice.conversa import conversar_por_voz

    optimus = _criar(args)
    agente = optimus.criar_agente(ao_evento=_mostrar_evento)
    try:
        conversar_por_voz(agente, optimus.config)
    except KeyboardInterrupt:
        print("\nAté logo!")
    except (ImportError, OSError) as erro:
        print(_c(f"Voz indisponível: {erro}\nInstale com: pip install "
                 "\"optimus-assistente[voz]\"", "91"))
        return 1
    return 0


def cmd_hardware(args) -> int:
    from optimus import hardware

    hw = hardware.detectar()
    perfil = hardware.escolher_perfil(hw)
    if args.json:
        print(json.dumps({"hardware": hw.para_dict(), "perfil": perfil.para_dict()},
                         ensure_ascii=False, indent=2))
    else:
        print(hardware.resumo(hw, perfil))
    return 0


def cmd_instalar_modelo(args) -> int:
    from optimus import hardware
    from optimus.engine import criar_motor

    config = cfg.carregar()
    motor = criar_motor(config)
    if not motor.disponivel():
        print(_c("O Ollama não está rodando. Instale em https://ollama.com e abra-o, ou rode o "
                 "instalador do Optimus.", "91"))
        return 1
    perfil = hardware.escolher_perfil(hardware.detectar())
    candidatos = [args.modelo] if args.modelo else [perfil.modelo, *perfil.alternativas]
    if not args.modelo and perfil.modelo_rapido not in candidatos:
        rapido = perfil.modelo_rapido
    else:
        rapido = ""
    for modelo in candidatos:
        print(f"Baixando {modelo} (perfil {perfil.nome})…")
        ultimo = [-1]

        def progresso(dados, ultimo=ultimo):
            if dados.get("total"):
                pct = int(100 * dados.get("completed", 0) / dados["total"])
                if pct != ultimo[0] and pct % 5 == 0:
                    ultimo[0] = pct
                    print(f"  {pct}%", end="\r", flush=True)

        if motor.baixar(modelo, progresso):
            print(_c(f"\n✓ {modelo} instalado.", "92"))
            config.definir("motor", "modelo", modelo)
            if rapido and motor.baixar(rapido, None):
                config.definir("motor", "modelo_rapido", rapido)
                print(_c(f"✓ Modelo rápido {rapido} instalado.", "92"))
            config.salvar()
            return 0
        print(_c(f"\nNão consegui baixar {modelo}, tentando a próxima opção…", "93"))
    return 1


def cmd_vozes(args) -> int:
    from optimus.voice import tts

    if args.baixar:
        print("Baixando vozes offline (Kokoro, ~120 MB)…")

        def progresso(nome, baixado, total):
            if total:
                print(f"  {nome}: {100 * baixado // total}%", end="\r", flush=True)

        ok = tts.baixar_kokoro(progresso)
        print(_c("\n✓ Vozes offline instaladas." if ok else "\nFalha ao baixar.",
                 "92" if ok else "91"))
        return 0 if ok else 1
    config = cfg.carregar()
    atual = tts.escolher_voz(config.get("voz", "voz"))
    print(f"Voz em uso: {atual.nome} ({atual.descricao})\n")
    for voz in tts.VOZES:
        pronta = (tts.kokoro_instalado() if voz.motor == "kokoro" else
                  tts.edge_instalado() if voz.motor == "edge" else True)
        marca = "✓" if pronta else " "
        print(f" {marca} {voz.id:42} {voz.genero:10} {voz.descricao}")
    print("\nTrocar: optimus config voz.voz masculina   (ou um id da lista)")
    if args.testar:
        tts.Falante(config.get("voz", "voz")).falar("Olá! Eu sou o Optimus. Tudo pronto.")
    return 0


def cmd_doutor(args) -> int:
    from optimus import hardware
    from optimus.engine import criar_motor
    from optimus.voice import tts

    config = cfg.carregar()
    ok = _c("✓", "92")
    falha = _c("✗", "91")
    aviso = _c("!", "93")
    print(f"Optimus {__version__} · Python {sys.version.split()[0]} · {sys.platform}")
    print(f"Pasta: {cfg.pasta_base()}")
    hw = hardware.detectar()
    perfil = hardware.escolher_perfil(hw)
    print(f"{ok} Hardware: {hw.cpu}, {hw.ram_total_gb} GB RAM, "
          f"{hw.placa.nome if hw.placa else 'sem placa dedicada'} → perfil {perfil.nome}")
    motor = criar_motor(config)
    if motor.disponivel():
        modelos = motor.modelos()
        alvo = config.get("motor", "modelo") or perfil.modelo
        presente = any(m == alvo or m.split(":")[0] == alvo.split(":")[0] for m in modelos)
        print(f"{ok} Motor {config.get('motor', 'backend')} ligado ({len(modelos)} modelos)")
        print(f"{ok if presente else aviso} Modelo {alvo} "
              f"{'instalado' if presente else 'não instalado: rode optimus instalar-modelo'}")
    else:
        print(f"{falha} Motor {config.get('motor', 'backend')} não responde em "
              f"{config.get('motor', 'url')}")
    for nome, modulo in (("Reconhecimento de voz (faster-whisper)", "faster_whisper"),
                         ("Microfone (sounddevice)", "sounddevice"),
                         ("Reprodução de áudio (miniaudio)", "miniaudio"),
                         ("Pesquisa na internet (ddgs)", "ddgs"),
                         ("Teclado e mouse (pyautogui)", "pyautogui"),
                         ("Bluetooth (bleak)", "bleak")):
        try:
            __import__(modulo)
            print(f"{ok} {nome}")
        except Exception:  # noqa: BLE001
            print(f"{aviso} {nome}: não instalado (opcional)")
    print(f"{ok if tts.kokoro_instalado() else aviso} Vozes offline Kokoro"
          f"{'' if tts.kokoro_instalado() else ': rode optimus vozes --baixar'}")
    print(f"{ok if tts.edge_instalado() else aviso} Vozes neurais online (edge-tts)")
    print(f"{ok if shutil.which('ffmpeg') else aviso} ffmpeg (câmeras rtsp)")
    print(f"Modo do agente: {config.get('agente', 'modo')} · casa: "
          f"{'configurada' if config.get('casa', 'url') else 'não configurada'}")
    return 0


def cmd_config(args) -> int:
    config = cfg.carregar()
    if not args.chave:
        if not config.caminho.exists():
            config.salvar()
        print(f"# {config.caminho}")
        print(cfg.para_toml(config.dados))
        return 0
    if "." not in args.chave or args.valor is None:
        print("Use: optimus config secao.chave valor   (ex.: optimus config voz.voz masculina)")
        return 1
    secao, chave = args.chave.split(".", 1)
    config.definir(secao, chave, cfg.converter_valor(args.valor))
    print(f"{args.chave} = {config.get(secao, chave)!r}  →  {config.salvar()}")
    return 0


def cmd_aprender(args) -> int:
    optimus = _criar()
    from optimus.tools.memoria import aprender

    agente = optimus.criar_agente()
    print(aprender(agente.contexto, args.fonte, args.titulo or "")["mensagem"])
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(prog="optimus", description="Optimus: assistente de IA "
                                     "local e autônomo. " + AVISO_LEGAL)
    parser.add_argument("--versao", action="version", version=f"Optimus {__version__}")
    parser.add_argument("--demo", action="store_true", help="usar o modo demonstração (sem IA)")
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("chat", help="conversa no terminal").set_defaults(func=cmd_chat)
    p = sub.add_parser("gui", help="interface visual no navegador")
    p.add_argument("--rede", action="store_true", help="liberar para celular/outros PCs da rede")
    p.add_argument("--porta", type=int, default=0)
    p.add_argument("--sem-navegador", action="store_true")
    p.set_defaults(func=cmd_gui)
    sub.add_parser("voz", help="conversa por voz").set_defaults(func=cmd_voz)
    p = sub.add_parser("tarefa", help="modo autônomo")
    p.add_argument("objetivo")
    p.set_defaults(func=cmd_tarefa)
    p = sub.add_parser("hardware", help="perfil de hardware")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_hardware)
    p = sub.add_parser("instalar-modelo", help="baixa o modelo ideal (Ollama)")
    p.add_argument("modelo", nargs="?")
    p.set_defaults(func=cmd_instalar_modelo)
    p = sub.add_parser("vozes", help="vozes disponíveis")
    p.add_argument("--baixar", action="store_true", help="instala as vozes offline")
    p.add_argument("--testar", action="store_true", help="fala uma frase de teste")
    p.set_defaults(func=cmd_vozes)
    sub.add_parser("doutor", help="diagnóstico").set_defaults(func=cmd_doutor)
    p = sub.add_parser("config", help="ver ou alterar configurações")
    p.add_argument("chave", nargs="?")
    p.add_argument("valor", nargs="?")
    p.set_defaults(func=cmd_config)
    p = sub.add_parser("aprender", help="estudar um site, arquivo ou texto")
    p.add_argument("fonte")
    p.add_argument("--titulo")
    p.set_defaults(func=cmd_aprender)
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args.func = cmd_chat
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
