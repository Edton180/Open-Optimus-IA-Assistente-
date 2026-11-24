"""Descoberta ativa e limitada de dispositivos na LAN privada local.

Não varre a internet nem aceita redes arbitrárias: o CIDR informado precisa ser uma
sub-rede privada de uma interface ativa deste computador e ter no máximo 256 endereços.
A descoberta usa ping e a tabela ARP/neighbor do sistema; não faz port scan nem tenta
autenticar, explorar ou alterar aparelhos.
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import platform
import re
import shutil
import socket
import subprocess
from typing import Iterable

import psutil

from optimus.safety import MODERADO
from optimus.tools.base import ferramenta, texto

_MAX_HOSTS = 256
_MAX_REDES = 4
_MAX_TRABALHADORES = 32


def redes_locais() -> list[dict]:
    """Retorna apenas redes IPv4 privadas de interfaces ativas, com no máximo /24."""
    saida = []
    estatisticas = psutil.net_if_stats()
    for nome, enderecos in psutil.net_if_addrs().items():
        status = estatisticas.get(nome)
        if status is not None and not status.isup:
            continue
        for endereco in enderecos:
            if endereco.family != socket.AF_INET or not endereco.netmask:
                continue
            try:
                ip = ipaddress.ip_address(endereco.address)
                rede = ipaddress.ip_network(f"{endereco.address}/{endereco.netmask}",
                                            strict=False)
            except ValueError:
                continue
            if not ip.is_private or ip.is_loopback or ip.is_link_local:
                continue
            if rede.num_addresses > _MAX_HOSTS:
                continue
            item = {"interface": nome, "ip_local": str(ip), "rede": str(rede)}
            if item not in saida:
                saida.append(item)
    return saida


def validar_rede(rede_solicitada: str, redes: Iterable[dict]) -> ipaddress.IPv4Network:
    """Impede varredura de rede pública ou fora das interfaces locais ativas."""
    try:
        rede = ipaddress.ip_network(rede_solicitada, strict=False)
    except ValueError as erro:
        raise ValueError("Informe uma rede IPv4 CIDR válida, por exemplo 192.168.1.0/24.") from erro
    if not isinstance(rede, ipaddress.IPv4Network) or not rede.is_private:
        raise ValueError("Por segurança, só é permitido descobrir redes IPv4 privadas.")
    if rede.num_addresses > _MAX_HOSTS:
        raise ValueError("A varredura é limitada a 256 endereços por execução.")
    locais = [ipaddress.ip_network(item["rede"]) for item in redes]
    if not any(rede.subnet_of(local) for local in locais):
        raise ValueError("A rede informada não pertence a uma interface privada ativa deste PC.")
    return rede


def _ping(ip: str, sistema: str | None = None) -> bool:
    sistema = (sistema or platform.system()).lower()
    if sistema == "windows":
        comando = ["ping", "-n", "1", "-w", "700", ip]
    elif sistema == "darwin":
        comando = ["ping", "-c", "1", "-W", "1000", ip]
    else:
        comando = ["ping", "-c", "1", "-W", "1", ip]
    try:
        r = subprocess.run(comando, capture_output=True, text=True, timeout=2.5, check=False)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _ler_vizinhos() -> dict[str, str]:
    """Lê cache ARP/neighbor e retorna IP -> MAC normalizado."""
    if platform.system().lower() == "windows":
        comando = ["arp", "-a"]
    elif shutil.which("ip"):
        comando = ["ip", "neigh"]
    else:
        comando = ["arp", "-an"]
    try:
        r = subprocess.run(comando, capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    texto_saida = r.stdout or ""
    if platform.system().lower() == "windows":
        pares = re.findall(r"(?i)(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-f]{2}(?:-[0-9a-f]{2}){5})",
                           texto_saida)
    else:
        pares = re.findall(r"(?i)(\d{1,3}(?:\.\d{1,3}){3})\)?\s+.*?\b"
                           r"([0-9a-f]{1,2}(?::[0-9a-f]{1,2}){5})\b", texto_saida)
    saida = {}
    for ip, mac in pares:
        try:
            ip_obj = ipaddress.ip_address(ip)
            octetos = re.split(r"[:-]", mac.lower())
            mac_normalizado = ":".join(p.zfill(2) for p in octetos)
            if ip_obj.is_private and mac_normalizado != "ff:ff:ff:ff:ff:ff":
                saida[str(ip_obj)] = mac_normalizado
        except ValueError:
            continue
    return saida


def descobrir(rede: ipaddress.IPv4Network, ip_local: str = "") -> dict:
    """Faz ping sweep limitado e cruza respostas com o cache ARP."""
    hosts = [str(ip) for ip in rede.hosts() if str(ip) != ip_local]
    respondendo = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_TRABALHADORES) as executor:
        futuros = {executor.submit(_ping, ip): ip for ip in hosts}
        for futuro in concurrent.futures.as_completed(futuros):
            ip = futuros[futuro]
            try:
                if futuro.result():
                    respondendo.add(ip)
            except Exception:
                continue
    vizinhos = _ler_vizinhos()
    ips = sorted(respondendo | (set(vizinhos) & set(hosts)),
                 key=lambda valor: int(ipaddress.ip_address(valor)))
    itens = []
    for ip in ips:
        itens.append({
            "ip": ip,
            "mac": vizinhos.get(ip, ""),
            "hostname": "",
            "fabricante": "não identificado (base OUI não instalada)",
            "estado": "respondendo ao ping" if ip in respondendo else "presente no cache ARP",
            "fontes": (["ping"] if ip in respondendo else []) +
                      (["ARP/neighbor"] if ip in vizinhos else []),
        })
    return {"rede": str(rede), "total": len(itens), "dispositivos": itens}


@ferramenta(
    "rede_wifi_varrer",
    "Descobre dispositivos na rede privada Wi-Fi/Ethernet local deste PC usando ping e ARP. "
    "Não varre redes públicas, não faz port scan e não altera aparelhos. Se necessário, informe "
    "um CIDR privado que pertença a uma interface local ativa e tenha até 256 endereços.",
    {"rede": texto("CIDR opcional da sub-rede local, ex.: 192.168.1.0/24")},
    grupo="casa", risco=MODERADO, obrigatorios=[],
)
def rede_wifi_varrer(ctx, rede: str = ""):
    interfaces = redes_locais()
    if not interfaces:
        return {"erro": "Não encontrei interface IPv4 privada ativa com sub-rede de até 256 endereços.",
                "interfaces": []}
    if rede:
        try:
            selecionada = validar_rede(rede, interfaces)
        except ValueError as erro:
            return {"erro": str(erro), "interfaces": interfaces}
        ip_local = next((i["ip_local"] for i in interfaces
                         if ipaddress.ip_address(i["ip_local"]) in selecionada), "")
        return descobrir(selecionada, ip_local)
    resultados = []
    for interface in interfaces[:_MAX_REDES]:
        rede_local = ipaddress.ip_network(interface["rede"])
        resultado = descobrir(rede_local, interface["ip_local"])
        resultado["interface"] = interface["interface"]
        resultados.append(resultado)
    return {
        "interfaces": interfaces,
        "redes_verificadas": len(resultados),
        "total": sum(r["total"] for r in resultados),
        "resultados": resultados,
        "limites": [
            "Dispositivos que bloqueiam ping e não aparecem no cache ARP podem não ser detectados.",
            "Fabricante OUI, portas e serviços não são inferidos nesta versão.",
            "A descoberta é limitada à LAN privada deste computador; não acessa a rede externa.",
        ],
    }
