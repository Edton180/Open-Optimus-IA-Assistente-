"""Controle do PC: comandos, programas, processos, energia e informações do sistema."""

from __future__ import annotations

import ast
import datetime as dt
import math
import operator
import re
import os
import shutil
import subprocess
import time
import webbrowser

import psutil

from optimus.safety import CRITICO, LIVRE, MODERADO, Avaliacao, risco_comando
from optimus.tools.base import ferramenta, numero, resolver, sistema, texto


def _risco_comando(args, ctx) -> Avaliacao:
    nivel = risco_comando(args.get("comando", ""))
    return Avaliacao(nivel, f"executar: {args.get('comando', '')}")


@ferramenta(
    "executar_comando",
    "Executa um comando no terminal do PC (PowerShell no Windows, bash no Linux/Android) e "
    "devolve a saída. Use para tarefas que nenhuma outra ferramenta cobre.",
    {"comando": texto("Comando completo"),
     "pasta": texto("Pasta onde rodar (opcional)"),
     "tempo_limite": numero("Segundos até desistir (padrão 60)")},
    grupo="comandos", risco=_risco_comando, obrigatorios=["comando"],
)
def executar_comando(ctx, comando: str, pasta: str = "", tempo_limite: int = 60):
    cwd = str(resolver(ctx, pasta)) if pasta else str(ctx.pasta_trabalho)
    if sistema() == "windows":
        programa = ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando]
    else:
        programa = [shutil.which("bash") or "/bin/sh", "-lc", comando]
    try:
        resultado = subprocess.run(programa, capture_output=True, text=True, cwd=cwd,
                                   timeout=max(1, min(int(tempo_limite or 60), 600)),
                                   encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"erro": f"O comando passou de {tempo_limite}s e foi interrompido."}
    saida = (resultado.stdout or "")[-12000:]
    erros = (resultado.stderr or "")[-4000:]
    return {"codigo": resultado.returncode, "saida": saida, "erros": erros}


@ferramenta(
    "info_sistema",
    "Mostra o estado do PC: CPU, uso de memória, disco, bateria, placa de vídeo e o perfil "
    "de IA escolhido.",
    grupo="programas",
)
def info_sistema(ctx):
    from optimus import hardware

    hw = hardware.detectar()
    perfil = ctx.perfil or hardware.escolher_perfil(hw)
    memoria = psutil.virtual_memory()
    raiz = "C:\\" if sistema() == "windows" else "/"
    disco = psutil.disk_usage(raiz)
    bateria = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    return {
        "sistema": f"{hw.sistema} {hw.versao_sistema}",
        "cpu": hw.cpu, "nucleos": hw.nucleos_fisicos, "threads": hw.nucleos_logicos,
        "cpu_uso_pct": psutil.cpu_percent(interval=0.3),
        "ram_total_gb": hw.ram_total_gb, "ram_uso_pct": memoria.percent,
        "disco_total_gb": round(disco.total / 1024**3, 1),
        "disco_livre_gb": round(disco.free / 1024**3, 1),
        "placa_video": hw.placa.nome if hw.placa else "sem placa dedicada",
        "vram_gb": hw.placa.vram_gb if hw.placa else 0,
        "bateria_pct": round(bateria.percent) if bateria else None,
        "na_tomada": bateria.power_plugged if bateria else None,
        "ligado_desde": dt.datetime.fromtimestamp(psutil.boot_time()).strftime("%d/%m %H:%M"),
        "perfil": perfil.nome, "modelo": perfil.modelo,
    }


@ferramenta(
    "listar_processos",
    "Lista os programas que mais usam CPU e memória agora.",
    {"limite": numero("Quantos mostrar")},
    grupo="programas", obrigatorios=[],
)
def listar_processos(ctx, limite: int = 15):
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(0.4)
    itens = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            itens.append({"pid": p.info["pid"], "nome": p.info["name"],
                          "cpu_pct": p.cpu_percent(None),
                          "memoria_mb": round(p.info["memory_info"].rss / 1024**2)})
        except (psutil.Error, AttributeError):
            continue
    itens.sort(key=lambda i: (i["cpu_pct"], i["memoria_mb"]), reverse=True)
    return {"total": len(itens), "itens": itens[: int(limite or 15)]}


@ferramenta(
    "encerrar_processo",
    "Fecha um programa pelo nome ou pelo número (PID).",
    {"alvo": texto("Nome do programa (ex.: chrome) ou PID")},
    grupo="programas", risco=lambda a, c: Avaliacao(CRITICO, f"encerrar {a.get('alvo')}"),
)
def encerrar_processo(ctx, alvo: str):
    alvo = str(alvo).strip()
    encerrados = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (alvo.isdigit() and p.info["pid"] == int(alvo)) or \
                    (not alvo.isdigit() and alvo.lower() in (p.info["name"] or "").lower()):
                if p.info["pid"] in (os.getpid(), os.getppid()):
                    continue
                p.terminate()
                encerrados.append(f"{p.info['name']} ({p.info['pid']})")
        except psutil.Error:
            continue
    if not encerrados:
        return {"erro": f"Nenhum processo encontrado para '{alvo}'"}
    return {"mensagem": "Encerrei: " + ", ".join(encerrados)}


_APELIDOS = {
    "windows": {"navegador": "start msedge", "bloco de notas": "notepad", "calculadora": "calc",
                "explorador": "explorer", "terminal": "wt", "configuracoes": "start ms-settings:",
                "gerenciador de tarefas": "taskmgr", "paint": "mspaint", "word": "start winword",
                "excel": "start excel", "spotify": "start spotify:", "whatsapp": "start whatsapp:"},
    "linux": {"navegador": "xdg-open https://", "bloco de notas": "gedit",
              "calculadora": "gnome-calculator", "explorador": "xdg-open ~",
              "terminal": "x-terminal-emulator", "configuracoes": "gnome-control-center",
              "gerenciador de tarefas": "gnome-system-monitor"},
}


def _risco_abrir(args, ctx) -> Avaliacao:
    alvo = str(args.get("alvo", ""))
    if alvo.startswith(("http://", "https://", "www.")):
        return Avaliacao(LIVRE, f"abrir site {alvo}")
    return Avaliacao(MODERADO, f"abrir {alvo}")


@ferramenta(
    "abrir",
    "Abre um site, arquivo, pasta ou programa (ex.: 'https://youtube.com', '~/Documentos', "
    "'calculadora', 'spotify', 'code').",
    {"alvo": texto("Link, caminho ou nome do programa")},
    grupo="programas", risco=_risco_abrir,
)
def abrir(ctx, alvo: str):
    alvo = alvo.strip()
    so = sistema()
    if alvo.startswith("www."):
        alvo = "https://" + alvo
    if alvo.startswith(("http://", "https://")):
        if so == "android" and shutil.which("termux-open-url"):
            subprocess.Popen(["termux-open-url", alvo])
        else:
            webbrowser.open(alvo)
        return {"mensagem": f"Abri {alvo}"}
    caminho = resolver(ctx, alvo)
    if caminho.exists():
        if so == "windows":
            os.startfile(str(caminho))  # type: ignore[attr-defined]
        elif so == "android":
            subprocess.Popen(["termux-open", str(caminho)])
        elif so == "macos":
            subprocess.Popen(["open", str(caminho)])
        else:
            subprocess.Popen(["xdg-open", str(caminho)], start_new_session=True)
        return {"mensagem": f"Abri {caminho}"}
    comando = _APELIDOS.get(so, {}).get(alvo.lower())
    if comando:
        subprocess.Popen(comando, shell=True, start_new_session=(so != "windows"))
        return {"mensagem": f"Abri {alvo}"}
    if shutil.which(alvo.split()[0]):
        subprocess.Popen(alvo.split(), start_new_session=(so != "windows"))
        return {"mensagem": f"Abri {alvo}"}
    if so == "windows":
        subprocess.Popen(f'start "" "{alvo}"', shell=True)
        return {"mensagem": f"Pedi ao Windows para abrir {alvo}"}
    if so == "android":
        return {"erro": f"Não achei '{alvo}'. No Android abro links e arquivos."}
    return {"erro": f"Não achei o programa '{alvo}' neste PC."}


_ENERGIA = {
    "windows": {"desligar": "shutdown /s /t 30", "reiniciar": "shutdown /r /t 30",
                "suspender": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                "bloquear": "rundll32.exe user32.dll,LockWorkStation", "cancelar": "shutdown /a"},
    "linux": {"desligar": "systemctl poweroff", "reiniciar": "systemctl reboot",
              "suspender": "systemctl suspend", "bloquear": "loginctl lock-session",
              "cancelar": "shutdown -c"},
}


@ferramenta(
    "energia",
    "Desliga, reinicia, suspende ou bloqueia o PC. 'cancelar' cancela um desligamento.",
    {"acao": {"type": "string", "enum": ["desligar", "reiniciar", "suspender", "bloquear",
                                         "cancelar"]}},
    grupo="programas",
    risco=lambda a, c: Avaliacao(MODERADO if a.get("acao") in ("bloquear", "cancelar")
                                 else CRITICO, f"{a.get('acao')} o computador"),
)
def energia(ctx, acao: str):
    comando = _ENERGIA.get(sistema(), {}).get(acao)
    if not comando:
        return {"erro": f"Ação '{acao}' não disponível neste sistema"}
    subprocess.Popen(comando, shell=True)
    return {"mensagem": f"Feito: {acao}."}


@ferramenta("data_hora", "Data, hora e dia da semana de agora.", grupo="geral")
def data_hora(ctx):
    agora = dt.datetime.now()
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    return {"data": agora.strftime("%d/%m/%Y"), "hora": agora.strftime("%H:%M"),
            "dia_semana": dias[agora.weekday()]}


_OPERADORES = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
               ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
               ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCOES = {n: getattr(math, n) for n in ("sqrt", "sin", "cos", "tan", "log", "log10", "exp",
                                          "floor", "ceil", "pi", "e")}
_FUNCOES.update({"abs": abs, "round": round, "min": min, "max": max})


def _avaliar(no):
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)):
        return no.value
    if isinstance(no, ast.BinOp) and type(no.op) in _OPERADORES:
        esquerda, direita = _avaliar(no.left), _avaliar(no.right)
        if isinstance(no.op, ast.Pow) and abs(direita) > 1000:
            raise ValueError("expoente grande demais")
        return _OPERADORES[type(no.op)](esquerda, direita)
    if isinstance(no, ast.UnaryOp) and type(no.op) in _OPERADORES:
        return _OPERADORES[type(no.op)](_avaliar(no.operand))
    if isinstance(no, ast.Name) and no.id in _FUNCOES:
        return _FUNCOES[no.id]
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in _FUNCOES:
        return _FUNCOES[no.func.id](*[_avaliar(a) for a in no.args])
    raise ValueError("expressão não permitida")


@ferramenta("calcular", "Faz contas com precisão (ex.: '(1500*12)*0.275', 'sqrt(81)').",
            {"expressao": texto("Expressão matemática")}, grupo="geral")
def calcular(ctx, expressao: str):
    expressao = re.sub(r"(?<=\d)\s*[x×]\s*(?=\d)", "*",
                       expressao.replace(",", ".").replace("^", "**"))
    return {"expressao": expressao, "resultado": _avaliar(ast.parse(expressao, mode="eval").body)}
