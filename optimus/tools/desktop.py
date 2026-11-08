"""Teclado, mouse, tela e área de transferência (extra opcional: pip install .[desktop]).

Fica desligado por padrão em [ferramentas] teclado_mouse, porque dá controle total da tela.
"""

from __future__ import annotations

import time
from pathlib import Path

from optimus.config import pasta_base
from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, numero, texto


def _pyautogui():
    try:
        import pyautogui
    except ImportError as erro:
        raise RuntimeError("Instale o extra de desktop: pip install optimus-assistente[desktop]"
                           ) from erro
    pyautogui.FAILSAFE = True  # mouse no canto superior esquerdo interrompe tudo
    return pyautogui


@ferramenta("digitar", "Digita um texto no programa que está em foco.",
            {"texto": texto("O que digitar")}, grupo="teclado_mouse", risco=MODERADO)
def digitar(ctx, texto: str):
    _pyautogui().write(texto, interval=0.02)
    return {"mensagem": "Digitei o texto."}


@ferramenta("teclas", "Aperta uma tecla ou atalho, ex.: 'enter', 'ctrl+c', 'alt+tab', "
            "'volumeup', 'playpause'.", {"atalho": texto("Tecla ou combinação com +")},
            grupo="teclado_mouse", risco=MODERADO)
def teclas(ctx, atalho: str):
    partes = [p.strip().lower() for p in atalho.split("+") if p.strip()]
    pg = _pyautogui()
    if len(partes) == 1:
        pg.press(partes[0])
    else:
        pg.hotkey(*partes)
    return {"mensagem": f"Apertei {atalho}."}


@ferramenta("clicar", "Clica numa posição da tela (x, y). Use captura_tela antes para ver.",
            {"x": numero("Posição horizontal"), "y": numero("Posição vertical"),
             "botao": texto("left, right ou middle")},
            grupo="teclado_mouse", risco=MODERADO, obrigatorios=["x", "y"])
def clicar(ctx, x: int, y: int, botao: str = "left"):
    _pyautogui().click(int(x), int(y), button=botao or "left")
    return {"mensagem": f"Cliquei em {x},{y}."}


@ferramenta("captura_tela", "Tira um print da tela e salva em arquivo.", grupo="teclado_mouse",
            risco=LIVRE)
def captura_tela(ctx):
    try:
        import mss
        import mss.tools
    except ImportError:
        return {"erro": "Instale o extra de desktop: pip install optimus-assistente[desktop]"}
    pasta = Path(pasta_base()) / "capturas"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"tela-{time.strftime('%Y%m%d-%H%M%S')}.png"
    with mss.mss() as tela:
        imagem = tela.grab(tela.monitors[0])
        mss.tools.to_png(imagem.rgb, imagem.size, output=str(destino))
        largura, altura = imagem.size
    return {"mensagem": f"Print salvo em {destino}", "largura": largura, "altura": altura}


@ferramenta("area_transferencia", "Lê o texto copiado (Ctrl+C) ou copia um texto novo.",
            {"novo_texto": texto("Se informado, copia este texto")}, grupo="teclado_mouse",
            risco=LIVRE, obrigatorios=[])
def area_transferencia(ctx, novo_texto: str = ""):
    try:
        import pyperclip
    except ImportError:
        return {"erro": "Instale o extra de desktop: pip install optimus-assistente[desktop]"}
    if novo_texto:
        pyperclip.copy(novo_texto)
        return {"mensagem": "Copiei o texto."}
    return {"texto": pyperclip.paste()[:10000]}
