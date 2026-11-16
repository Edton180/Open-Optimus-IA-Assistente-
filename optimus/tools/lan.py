"""Controle de aparelhos na rede Wi-Fi **sem Home Assistant**.

Primeiro protocolo suportado: TP-Link Kasa (tomadas, interruptores e lâmpadas inteligentes
HS100/HS110/KP105/KL130...). É um protocolo local simples, sobre TCP/UDP na porta 9999, com
uma cifra XOR de chave encadeada (sem nuvem, sem conta). Dá para descobrir os aparelhos na
rede e ligar, desligar, alternar e ajustar o brilho — tudo dentro da sua própria casa.

Outros aparelhos (Tuya, Wiz, Yeelight...) podem entrar depois seguindo o mesmo formato, ou
pelo Home Assistant, que cobre milhares de marcas.
"""

from __future__ import annotations

import json
import socket

from optimus.safety import MODERADO
from optimus.tools.base import ferramenta, numero, texto

PORTA_KASA = 9999
_CHAVE_INICIAL = 171  # 0xAB, definido pelo protocolo da TP-Link


def cifrar_kasa(texto_claro: str) -> bytes:
    """Cifra XOR encadeada da Kasa (a chave de cada byte é o byte cifrado anterior)."""
    chave = _CHAVE_INICIAL
    saida = bytearray()
    for caractere in texto_claro.encode("utf-8"):
        chave = chave ^ caractere
        saida.append(chave)
    return bytes(saida)


def decifrar_kasa(dados: bytes) -> str:
    chave = _CHAVE_INICIAL
    saida = bytearray()
    for byte in dados:
        saida.append(chave ^ byte)
        chave = byte
    return saida.decode("utf-8", errors="replace")


def payload_kasa(acao: str, valor: str = "") -> dict:
    """Monta o JSON de comando da Kasa para a ação pedida (sem rede, fácil de testar)."""
    acao = (acao or "").lower().strip()
    if acao in ("estado", "status", "info"):
        return {"system": {"get_sysinfo": {}}}
    if acao in ("ligar", "on", "acender"):
        return {"system": {"set_relay_state": {"state": 1}}}
    if acao in ("desligar", "off", "apagar"):
        return {"system": {"set_relay_state": {"state": 0}}}
    if acao in ("brilho", "brightness", "escurecer", "clarear"):
        nivel = max(1, min(100, int(float(valor or 50))))
        # Lâmpadas usam o serviço de iluminação; tomadas com dimmer, o smartlife.iot.dimmer.
        return {"smartlife.iot.smartbulb.lightingservice":
                {"transition_light_state": {"on_off": 1, "brightness": nivel}}}
    raise ValueError(f"Ação Kasa desconhecida: {acao!r} "
                     "(use ligar, desligar, alternar, brilho ou estado).")


def _quadro_tcp(mensagem: bytes) -> bytes:
    # Na porta TCP, a Kasa espera 4 bytes de tamanho (big-endian) antes do corpo cifrado.
    return len(mensagem).to_bytes(4, "big") + mensagem


def _enviar_tcp(host: str, comando: dict, timeout: float = 5.0) -> dict:
    cifrado = cifrar_kasa(json.dumps(comando))
    with socket.create_connection((host, PORTA_KASA), timeout=timeout) as sock:
        sock.sendall(_quadro_tcp(cifrado))
        cabecalho = _ler_n(sock, 4)
        tamanho = int.from_bytes(cabecalho, "big")
        corpo = _ler_n(sock, tamanho)
    return json.loads(decifrar_kasa(corpo))


def _ler_n(sock: socket.socket, n: int) -> bytes:
    dados = bytearray()
    while len(dados) < n:
        pedaco = sock.recv(n - len(dados))
        if not pedaco:
            break
        dados.extend(pedaco)
    return bytes(dados)


def _nome_e_estado(sysinfo: dict) -> dict:
    info = sysinfo.get("system", {}).get("get_sysinfo", sysinfo)
    nome = info.get("alias") or info.get("dev_name") or "aparelho Kasa"
    ligado = info.get("relay_state")
    if ligado is None and "light_state" in info:  # lâmpadas
        ligado = info["light_state"].get("on_off")
    return {"nome": nome, "ligado": bool(ligado), "modelo": info.get("model", "")}


@ferramenta(
    "kasa_procurar",
    "Procura tomadas, interruptores e lâmpadas TP-Link Kasa na rede Wi-Fi da casa, sem precisar "
    "do Home Assistant. Devolve nome, modelo, estado e o IP de cada um (use no kasa_controlar).",
    {"segundos": numero("Tempo de busca (padrão 3)")},
    grupo="casa", obrigatorios=[],
)
def kasa_procurar(ctx, segundos: float = 3):
    pergunta = cifrar_kasa(json.dumps({"system": {"get_sysinfo": {}}}))
    achados = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(max(0.5, min(float(segundos), 10)))
        try:
            sock.sendto(pergunta, ("255.255.255.255", PORTA_KASA))
        except OSError as erro:
            return {"erro": f"Não consegui enviar na rede: {erro}"}
        vistos = set()
        while True:
            try:
                dados, (ip, _porta) = sock.recvfrom(4096)
            except socket.timeout:
                break
            except OSError:
                break
            if ip in vistos:
                continue
            vistos.add(ip)
            try:
                info = _nome_e_estado(json.loads(decifrar_kasa(dados)))
            except (ValueError, KeyError):
                continue
            info["ip"] = ip
            achados.append(info)
    return {"total": len(achados), "aparelhos": achados}


@ferramenta(
    "kasa_controlar",
    "Liga, desliga, alterna ou ajusta o brilho de um aparelho TP-Link Kasa na rede Wi-Fi, sem "
    "Home Assistant. Informe o IP (veja no kasa_procurar). Ações: ligar, desligar, alternar, "
    "brilho (valor 0-100), estado.",
    {"ip": texto("IP do aparelho na rede, ex.: 192.168.0.42"),
     "acao": texto("ligar, desligar, alternar, brilho ou estado"),
     "valor": texto("Opcional: brilho 0-100")},
    grupo="casa", risco=MODERADO, obrigatorios=["ip", "acao"],
)
def kasa_controlar(ctx, ip: str, acao: str, valor: str = ""):
    acao = (acao or "").lower().strip()
    try:
        if acao in ("alternar", "toggle"):
            atual = _nome_e_estado(_enviar_tcp(ip, payload_kasa("estado")))
            acao = "desligar" if atual["ligado"] else "ligar"
        resposta = _enviar_tcp(ip, payload_kasa(acao, valor))
    except ValueError as erro:
        return {"erro": str(erro)}
    except OSError as erro:
        return {"erro": f"Não consegui falar com o aparelho em {ip}: {erro}. "
                        "Confira se é um Kasa e se está na mesma rede."}
    if acao in ("estado", "status", "info"):
        return _nome_e_estado(resposta)
    erro = _erro_kasa(resposta)
    if erro:
        return {"erro": f"O aparelho recusou: {erro}"}
    return {"mensagem": f"Feito: {acao} em {ip}."}


def _erro_kasa(resposta: dict) -> str:
    for secao in resposta.values():
        if isinstance(secao, dict):
            for metodo in secao.values():
                if isinstance(metodo, dict) and metodo.get("err_code", 0) != 0:
                    return metodo.get("err_msg", "erro desconhecido")
    return ""
