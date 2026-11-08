"""Casa inteligente: Home Assistant, Bluetooth, câmeras e rede local.

O caminho principal é o Home Assistant, que já fala com milhares de aparelhos por Wi-Fi,
Bluetooth, Zigbee, Matter e infravermelho (controles de TV e ar-condicionado com Broadlink,
por exemplo), além de câmeras. O Optimus conversa com ele pela API REST: basta pôr a URL e
um token de acesso em [casa] no config.toml.

Também dá para, sem Home Assistant:
- procurar aparelhos Bluetooth por perto (extra opcional: pip install bleak);
- tirar foto de uma câmera IP (link http de snapshot ou rtsp com ffmpeg);
- listar os aparelhos conectados no Wi-Fi da casa.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from optimus.config import pasta_base
from optimus.safety import CRITICO, LIVRE, MODERADO, Avaliacao
from optimus.tools.base import ferramenta, numero, sistema, texto

_SENSIVEIS = ("lock", "alarm_control_panel", "cover.garage", "garage", "siren", "valve")

_SERVICOS = {
    "ligar": "turn_on", "desligar": "turn_off", "alternar": "toggle",
    "abrir": "open_cover", "fechar": "close_cover", "parar": "stop_cover",
    "trancar": "lock", "destrancar": "unlock", "tocar": "media_play", "pausar": "media_pause",
    "proxima": "media_next_track", "volume": "volume_set", "temperatura": "set_temperature",
    "comando": "send_command", "ativar": "turn_on",
}


def _ha(ctx) -> tuple[str, dict[str, str]]:
    url = (ctx.config.get("casa", "url") or "").rstrip("/")
    token = ctx.config.get("casa", "token") or ""
    if not url or not token:
        raise RuntimeError("Configure [casa] url e token (Home Assistant) no config.toml ou "
                           "na tela Configurações > Casa.")
    return url, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@ferramenta(
    "casa_dispositivos",
    "Lista os aparelhos da casa no Home Assistant (luzes, tomadas, ar-condicionado, TV, "
    "fechaduras, câmeras, sensores) com o estado atual. Filtre por tipo ou nome.",
    {"filtro": texto("Tipo (light, switch, climate, media_player, camera, lock...) ou nome")},
    grupo="casa", obrigatorios=[],
)
def casa_dispositivos(ctx, filtro: str = ""):
    url, cabecalho = _ha(ctx)
    estados = httpx.get(f"{url}/api/states", headers=cabecalho, timeout=15).json()
    filtro = (filtro or "").lower()
    itens = []
    for e in estados:
        nome = e.get("attributes", {}).get("friendly_name", e["entity_id"])
        if filtro and filtro not in e["entity_id"].lower() and filtro not in nome.lower():
            continue
        if e["entity_id"].split(".")[0] in ("automation", "script", "zone", "person", "sun",
                                            "update", "device_tracker") and not filtro:
            continue
        itens.append({"nome": nome, "id": e["entity_id"], "estado": e["state"]})
    return {"total": len(itens), "itens": itens[:150]}


def _risco_casa(args, ctx) -> Avaliacao:
    entidade = str(args.get("id", "")).lower()
    acao = str(args.get("acao", "")).lower()
    if any(s in entidade for s in _SENSIVEIS) or acao in ("destrancar", "abrir") and \
            "garage" in entidade:
        return Avaliacao(CRITICO, f"{acao} {entidade} (segurança da casa)")
    return Avaliacao(MODERADO, f"{acao} {entidade}")


@ferramenta(
    "casa_controlar",
    "Controla um aparelho da casa pelo Home Assistant. Ações: ligar, desligar, alternar, abrir, "
    "fechar, trancar, destrancar, tocar, pausar, volume, temperatura, comando (infravermelho).",
    {"id": texto("Id do aparelho, ex.: light.sala (use casa_dispositivos para descobrir)"),
     "acao": texto("O que fazer"),
     "valor": texto("Opcional: brilho 0-100, temperatura, volume 0-100 ou nome do comando IR")},
    grupo="casa", risco=_risco_casa, obrigatorios=["id", "acao"],
)
def casa_controlar(ctx, id: str, acao: str, valor: str = ""):
    url, cabecalho = _ha(ctx)
    dominio = id.split(".")[0]
    servico = _SERVICOS.get(acao.lower(), acao.lower())
    dados: dict = {"entity_id": id}
    if valor:
        if servico == "volume_set":
            dados["volume_level"] = max(0, min(100, float(valor))) / 100
        elif servico == "set_temperature":
            dados["temperature"] = float(valor)
        elif servico == "send_command":
            dados["command"] = valor
        elif dominio == "light" and servico == "turn_on":
            dados["brightness_pct"] = max(1, min(100, int(float(valor))))
    if dominio == "cover" and servico in ("turn_on", "turn_off"):
        servico = "open_cover" if servico == "turn_on" else "close_cover"
    if servico in ("turn_on", "turn_off", "toggle") and dominio not in (
            "light", "switch", "fan", "climate", "media_player", "input_boolean", "remote",
            "humidifier", "vacuum", "siren", "automation", "script", "scene"):
        dominio = "homeassistant"
    resposta = httpx.post(f"{url}/api/services/{dominio}/{servico}", headers=cabecalho,
                          json=dados, timeout=15)
    resposta.raise_for_status()
    return {"mensagem": f"Feito: {acao} em {id}."}


def _salvar_foto(conteudo: bytes, nome: str) -> Path:
    pasta = pasta_base() / "cameras"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{re.sub(r'[^a-z0-9_-]', '_', nome.lower())}-{time.strftime('%H%M%S')}.jpg"
    destino.write_bytes(conteudo)
    return destino


@ferramenta(
    "camera_foto",
    "Tira uma foto de uma câmera: id do Home Assistant (camera.portao) ou link da câmera IP "
    "(http://.../snapshot.jpg ou rtsp://...). Salva a imagem e diz onde ficou.",
    {"camera": texto("Id camera.xxx ou link http/rtsp")},
    grupo="casa", risco=LIVRE,
)
def camera_foto(ctx, camera: str):
    if camera.startswith("camera."):
        url, cabecalho = _ha(ctx)
        resposta = httpx.get(f"{url}/api/camera_proxy/{camera}", headers=cabecalho, timeout=20)
        resposta.raise_for_status()
        return {"mensagem": f"Foto salva em {_salvar_foto(resposta.content, camera)}"}
    if camera.startswith("rtsp://"):
        if not shutil.which("ffmpeg"):
            return {"erro": "Para câmeras rtsp instale o ffmpeg."}
        resultado = subprocess.run(["ffmpeg", "-loglevel", "error", "-rtsp_transport", "tcp",
                                    "-i", camera, "-frames:v", "1", "-f", "image2", "-"],
                                   capture_output=True, timeout=30, check=False)
        if not resultado.stdout:
            return {"erro": resultado.stderr.decode(errors="replace")[:300]}
        return {"mensagem": f"Foto salva em {_salvar_foto(resultado.stdout, 'camera')}"}
    resposta = httpx.get(camera, timeout=20, follow_redirects=True)
    resposta.raise_for_status()
    return {"mensagem": f"Foto salva em {_salvar_foto(resposta.content, 'camera')}"}


@ferramenta(
    "bluetooth_procurar",
    "Procura aparelhos Bluetooth por perto (fones, relógios, lâmpadas, sensores).",
    {"segundos": numero("Quanto tempo procurar (padrão 6)")},
    grupo="casa", obrigatorios=[],
)
def bluetooth_procurar(ctx, segundos: int = 6):
    try:
        from bleak import BleakScanner
    except ImportError:
        return {"erro": "Instale o suporte a Bluetooth: pip install bleak"}

    async def procurar():
        return await BleakScanner.discover(timeout=max(2, min(int(segundos or 6), 30)),
                                           return_adv=True)

    achados = asyncio.run(procurar())
    itens = [{"nome": d.name or "(sem nome)", "endereco": d.address, "sinal": adv.rssi}
             for d, adv in achados.values()]
    itens.sort(key=lambda i: i["sinal"], reverse=True)
    return {"total": len(itens), "itens": itens}


@ferramenta(
    "rede_local",
    "Lista os aparelhos que este PC enxerga na rede Wi-Fi/cabo da casa (IP e endereço MAC).",
    grupo="casa",
)
def rede_local(ctx):
    if sistema() == "windows":
        saida = subprocess.run(["arp", "-a"], capture_output=True, text=True, check=False).stdout
        padrao = r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f-]{17})"
    else:
        comando = ["ip", "neigh"] if shutil.which("ip") else ["arp", "-an"]
        saida = subprocess.run(comando, capture_output=True, text=True, check=False).stdout
        padrao = r"(\d+\.\d+\.\d+\.\d+).*?([0-9a-f:]{17})"
    itens = [{"nome": ip, "mac": mac} for ip, mac in re.findall(padrao, saida.lower())]
    return {"total": len(itens), "itens": itens}
