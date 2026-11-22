"""Ditado em qualquer programa: um botão flutuante (sempre por cima) que escuta e digita.

`optimus ditado` abre o botão 🎙. Clique para ligar, fale, e o texto aparece onde o cursor
estiver (Word, navegador, WhatsApp Web, bloco de notas...). Clique de novo para desligar.
`optimus ditado --sem-janela` faz o mesmo pelo terminal (Ctrl+C para parar).

Comandos falados: "vírgula", "ponto final", "ponto de interrogação", "ponto de exclamação",
"dois pontos", "ponto e vírgula", "nova linha", "novo parágrafo", "abre aspas", "fecha aspas",
"abre parênteses", "fecha parênteses", "travessão".

Precisa de: microfone (`pip install sounddevice`), transcrição (faster-whisper ou
sherpa-onnx) e, para digitar, `pip install pyautogui pyperclip`.
"""

from __future__ import annotations

import re
import sys
import tempfile
import threading
from pathlib import Path

_COMANDOS = [  # (o que a pessoa fala, o que entra no texto); os mais longos primeiro
    (r"novo par[aá]grafo", "\n\n"), (r"nova linha|pr[oó]xima linha|pula linha", "\n"),
    (r"ponto de interroga[cç][aã]o", "?"), (r"ponto de exclama[cç][aã]o", "!"),
    (r"ponto e v[ií]rgula", ";"), (r"ponto final|ponto par[aá]grafo", "."),
    (r"dois pontos", ":"), (r"v[ií]rgula", ","), (r"retic[eê]ncias", "..."),
    (r"abre aspas", " “"), (r"fecha aspas", "”"),
    (r"abre par[eê]nteses?", " ("), (r"fecha par[eê]nteses?", ")"), (r"travess[aã]o", " — "),
]
_JUNTO_ANTES = ".,;:!?)”"


def processar(texto: str, anterior: str = "") -> str:
    """Troca os comandos falados por pontuação e arruma maiúsculas e espaços.

    `anterior`: o que já foi digitado (para saber se começa frase nova)."""
    t = " " + (texto or "").strip() + " "
    for falado, sinal in _COMANDOS:
        t = re.sub(rf"[\s,.]*\b(?:{falado})\b[\s,.]*", f"\x00{sinal}\x00", t, flags=re.IGNORECASE)
    saida = ""
    for p in t.split("\x00"):
        if not p.strip() and "\n" not in p:
            continue
        if p[0] in _JUNTO_ANTES or p.startswith("\n"):
            saida = saida.rstrip(" ") + p
        else:
            pedaco = p.strip()
            separador = "" if not saida or saida.endswith((" ", "\n", "(", "“")) else " "
            saida += separador + pedaco
    saida = re.sub(r"[ \t]+", " ", saida).replace(" \n", "\n")
    # maiúscula no começo e depois de . ! ? e de parágrafo
    contexto = (anterior or "").rstrip(" ")
    comeca_frase = not contexto or contexto.endswith((".", "!", "?", "\n"))
    letras = list(saida)
    proxima_maiuscula = comeca_frase
    for i, c in enumerate(letras):
        if c.isalpha():
            if proxima_maiuscula:
                letras[i] = c.upper()
            proxima_maiuscula = False
        elif c in ".!?\n":
            proxima_maiuscula = True
    saida = "".join(letras)
    if anterior and not anterior[-1].isspace() and saida and saida[0] not in _JUNTO_ANTES \
            and not saida.startswith(("\n", " ")):
        saida = " " + saida
    return saida


def digitar(texto: str) -> bool:
    """Põe o texto onde o cursor está. Usa colar (aceita acentos em qualquer teclado)."""
    if not texto:
        return True
    try:
        import pyautogui
    except Exception:  # noqa: BLE001 - sem tela ou sem pyautogui
        return False
    try:
        import pyperclip

        antes = None
        try:
            antes = pyperclip.paste()
        except Exception:  # noqa: BLE001 - área de transferência vazia ou indisponível
            antes = None
        pyperclip.copy(texto)
        pyautogui.hotkey("command" if sys.platform == "darwin" else "ctrl", "v")
        if antes is not None:
            threading.Timer(0.6, lambda: pyperclip.copy(antes)).start()
    except ImportError:
        pyautogui.write(texto, interval=0.01)
    return True


def _transcrever(amostras, idioma: str, config) -> str:
    from optimus.estudio import audio, transcrever

    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "ditado.wav"
        arquivo.write_bytes(audio.wav_bytes(amostras, 16000))
        trechos, _ = transcrever.transcrever(arquivo, idioma or "pt-BR", config=config)
    return " ".join(t.texto for t in trechos).strip()


class Ditado:
    """Escuta em segundo plano e digita cada frase assim que a pessoa para de falar."""

    def __init__(self, idioma: str = "pt-BR", config=None, ao_mudar=None):
        self.idioma = idioma
        self.config = config
        self.ao_mudar = ao_mudar or (lambda estado, texto="": None)
        self.ligado = False
        self._linha: threading.Thread | None = None
        self._digitado = ""

    def alternar(self) -> bool:
        if self.ligado:
            self.parar()
        else:
            self.iniciar()
        return self.ligado

    def iniciar(self) -> None:
        if self.ligado:
            return
        self.ligado = True
        self._linha = threading.Thread(target=self._rodar, daemon=True)
        self._linha.start()

    def parar(self) -> None:
        self.ligado = False
        self.ao_mudar("parado")

    def _rodar(self) -> None:
        from optimus.voice.stt import gravar_ate_silencio

        while self.ligado:
            self.ao_mudar("ouvindo")
            try:
                amostras = gravar_ate_silencio(espera_inicial=4.0, maximo=25.0)
            except Exception as erro:  # noqa: BLE001 - sem microfone
                self.ao_mudar("erro", f"Microfone: {erro}")
                self.ligado = False
                return
            if amostras is None or not self.ligado:
                continue
            self.ao_mudar("escrevendo")
            try:
                falado = _transcrever(amostras, self.idioma, self.config)
            except Exception as erro:  # noqa: BLE001 - sem motor de transcrição
                self.ao_mudar("erro", str(erro))
                self.ligado = False
                return
            texto = processar(falado, self._digitado)
            if texto.strip() and self.ligado:
                if not digitar(texto):
                    self.ao_mudar("erro", "Para digitar, instale: pip install pyautogui pyperclip")
                    self.ligado = False
                    return
                self._digitado = (self._digitado + texto)[-200:]
                self.ao_mudar("digitado", texto)


def _sem_roubar_foco(janela) -> None:
    """No Windows, clicar no botão não tira o cursor do programa onde você está escrevendo."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetParent(janela.winfo_id())
        estilo = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, estilo | 0x08000000 | 0x00000080)
    except Exception:  # noqa: BLE001 - só um conforto a mais
        pass


def janela(idioma: str = "pt-BR", config=None) -> None:
    """O botão flutuante. Arraste para mudar de lugar; botão direito fecha."""
    import tkinter as tk

    raiz = tk.Tk()
    raiz.title("Ditado - Optimus")
    raiz.overrideredirect(True)
    raiz.attributes("-topmost", True)
    try:
        raiz.attributes("-alpha", 0.92)
    except tk.TclError:
        pass
    largura, altura = 190, 56
    raiz.geometry(f"{largura}x{altura}+{raiz.winfo_screenwidth() - largura - 30}+"
                  f"{raiz.winfo_screenheight() - altura - 90}")
    raiz.configure(bg="#0b1220")
    botao = tk.Label(raiz, text="🎙", font=("Segoe UI Emoji", 20), bg="#1b2a44", fg="white",
                     width=2, cursor="hand2")
    botao.pack(side="left", padx=8, pady=8)
    rotulo = tk.Label(raiz, text="Clique para ditar", bg="#0b1220", fg="#cfe3ff",
                      font=("Segoe UI", 9), wraplength=120, justify="left")
    rotulo.pack(side="left", fill="both", expand=True)
    cores = {"ouvindo": "#e0245e", "escrevendo": "#f5a623", "digitado": "#e0245e",
             "parado": "#1b2a44", "erro": "#7a1f1f"}
    textos = {"ouvindo": "Ouvindo…", "escrevendo": "Escrevendo…", "parado": "Clique para ditar"}

    def mudar(estado: str, texto: str = "") -> None:
        def aplicar():
            botao.configure(bg=cores.get(estado, "#1b2a44"))
            rotulo.configure(text=(texto[:60] if estado in ("erro", "digitado") else
                                   textos.get(estado, "")))
        raiz.after(0, aplicar)

    ditado = Ditado(idioma, config, mudar)
    inicio = {"x": 0, "y": 0, "moveu": False}

    def pegar(e):
        inicio.update(x=e.x_root - raiz.winfo_x(), y=e.y_root - raiz.winfo_y(), moveu=False)

    def arrastar(e):
        inicio["moveu"] = True
        raiz.geometry(f"+{e.x_root - inicio['x']}+{e.y_root - inicio['y']}")

    def soltar(_e):
        if not inicio["moveu"]:
            ditado.alternar()

    for alvo in (botao, rotulo, raiz):
        alvo.bind("<ButtonPress-1>", pegar)
        alvo.bind("<B1-Motion>", arrastar)
        alvo.bind("<ButtonRelease-1>", soltar)
        alvo.bind("<Button-3>", lambda _e: (ditado.parar(), raiz.destroy()))
    raiz.update_idletasks()
    _sem_roubar_foco(raiz)
    raiz.mainloop()


def terminal(idioma: str = "pt-BR", config=None) -> None:
    def mostrar(estado: str, texto: str = "") -> None:
        if estado == "digitado":
            print(f"✍️  {texto.strip()}")
        elif estado == "erro":
            print(f"⚠️  {texto}")

    ditado = Ditado(idioma, config, mostrar)
    print("Ditado ligado: fale, e o texto vai para onde o cursor estiver. Ctrl+C para parar.")
    ditado.iniciar()
    try:
        while ditado.ligado and ditado._linha is not None:
            ditado._linha.join(0.5)
    except KeyboardInterrupt:
        ditado.parar()
