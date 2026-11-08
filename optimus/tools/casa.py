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
    return _controlar(ctx, id, acao, valor)


def _controlar(ctx, id: str, acao: str, valor: str = "") -> dict:
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


def _foto(conteudo: bytes, nome: str) -> dict:
    destino = _salvar_foto(conteudo, nome)
    return {"mensagem": f"Foto salva em {destino}", "imagem": f"/api/midia/cameras/{destino.name}",
            "arquivo": str(destino)}


def imagem_da_camera(config, camera: str) -> bytes:
    """Uma imagem atual da câmera (id do Home Assistant, link http ou rtsp). Usado pela tela
    da casa para mostrar a câmera ao vivo (uma imagem nova a cada segundo)."""
    if camera.startswith("ip:"):
        lista = config.dados.get("cameras") or []
        indice = int(camera[3:]) if camera[3:].isdigit() else -1
        if not 0 <= indice < len(lista) or not isinstance(lista[indice], dict):
            raise RuntimeError("câmera desconhecida")
        camera = str(lista[indice].get("url", ""))
    if camera.startswith("camera."):
        url = (config.get("casa", "url") or "").rstrip("/")
        token = config.get("casa", "token") or ""
        if not url or not token:
            raise RuntimeError("Home Assistant não configurado")
        resposta = httpx.get(f"{url}/api/camera_proxy/{camera}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=10)
        resposta.raise_for_status()
        return resposta.content
    if camera.startswith("rtsp://"):
        if not shutil.which("ffmpeg"):
            raise RuntimeError("Para câmeras rtsp instale o ffmpeg")
        resultado = subprocess.run(["ffmpeg", "-loglevel", "error", "-rtsp_transport", "tcp",
                                    "-i", camera, "-frames:v", "1", "-f", "image2", "-"],
                                   capture_output=True, timeout=15, check=False)
        if not resultado.stdout:
            raise RuntimeError(resultado.stderr.decode(errors="replace")[:200])
        return resultado.stdout
    if camera.startswith(("http://", "https://")):
        resposta = httpx.get(camera, timeout=10, follow_redirects=True)
        resposta.raise_for_status()
        return resposta.content
    raise RuntimeError("câmera desconhecida")


def cameras_configuradas(config) -> list[dict]:
    """Câmeras do Home Assistant + câmeras IP de [[cameras]] (nome, url) no config.toml."""
    # Câmeras IP viram "ip:N": o link (que pode ter usuário e senha) nunca vai para a tela.
    itens = [{"nome": c.get("nome") or f"Câmera {i + 1}", "id": f"ip:{i}"}
             for i, c in enumerate(config.dados.get("cameras") or [])
             if isinstance(c, dict) and c.get("url")]
    url = (config.get("casa", "url") or "").rstrip("/")
    token = config.get("casa", "token") or ""
    if url and token:
        try:
            estados = httpx.get(f"{url}/api/states", timeout=10,
                                headers={"Authorization": f"Bearer {token}"}).json()
            itens += [{"nome": e.get("attributes", {}).get("friendly_name", e["entity_id"]),
                       "id": e["entity_id"]} for e in estados
                      if e["entity_id"].startswith("camera.")]
        except (httpx.HTTPError, ValueError, KeyError):
            pass
    return itens


@ferramenta(
    "cameras_listar",
    "Lista as câmeras da casa (Home Assistant e câmeras IP configuradas). A tela Casa mostra "
    "a imagem ao vivo de cada uma.",
    grupo="casa",
)
def cameras_listar(ctx):
    itens = cameras_configuradas(ctx.config)
    if not itens:
        return {"erro": "Nenhuma câmera configurada. Ligue o Home Assistant ou adicione câmeras "
                        "IP em [[cameras]] no config.toml."}
    return {"total": len(itens), "itens": itens}


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
        return _foto(resposta.content, camera)
    if camera.startswith("rtsp://"):
        if not shutil.which("ffmpeg"):
            return {"erro": "Para câmeras rtsp instale o ffmpeg."}
        resultado = subprocess.run(["ffmpeg", "-loglevel", "error", "-rtsp_transport", "tcp",
                                    "-i", camera, "-frames:v", "1", "-f", "image2", "-"],
                                   capture_output=True, timeout=30, check=False)
        if not resultado.stdout:
            return {"erro": resultado.stderr.decode(errors="replace")[:300]}
        return _foto(resultado.stdout, "camera")
    resposta = httpx.get(camera, timeout=20, follow_redirects=True)
    resposta.raise_for_status()
    return _foto(resposta.content, "camera")


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


def _risco_varios(args, ctx) -> Avaliacao:
    pior = Avaliacao(MODERADO, "vários comandos na casa")
    for passo in args.get("comandos") or []:
        if isinstance(passo, dict):
            avaliacao = _risco_casa(passo, ctx)
            if avaliacao.nivel > pior.nivel:
                pior = avaliacao
    return pior


@ferramenta(
    "casa_varios",
    "Executa vários comandos na casa de uma vez, em ordem (ex.: apagar todas as luzes e ligar "
    "o ar). Cada comando tem id, acao e valor opcional.",
    {"comandos": {"type": "array", "description": "Lista de comandos",
                  "items": {"type": "object", "properties": {
                      "id": {"type": "string"}, "acao": {"type": "string"},
                      "valor": {"type": "string"}}, "required": ["id", "acao"]}}},
    grupo="casa", risco=_risco_varios,
)
def casa_varios(ctx, comandos: list):
    feitos, erros = [], []
    for passo in (comandos or [])[:20]:
        try:
            _controlar(ctx, str(passo.get("id", "")), str(passo.get("acao", "")),
                       str(passo.get("valor", "") or ""))
            feitos.append(f"{passo.get('acao')} {passo.get('id')}")
        except Exception as erro:  # noqa: BLE001 - um aparelho falhar não para os outros
            erros.append(f"{passo.get('id')}: {erro}")
    return {"mensagem": f"{len(feitos)} comando(s) feitos.", "feitos": feitos, "erros": erros}


_PALAVRAS_SENSIVEIS = re.compile(
    r"(destran[cq]|tran[cq]|fechadura|port[aã]o|alarme|garagem|sirene)", re.I)


def _risco_falar(args, ctx) -> Avaliacao:
    texto_pedido = str(args.get("texto", ""))
    if _PALAVRAS_SENSIVEIS.search(texto_pedido):
        return Avaliacao(CRITICO, f"pedir à casa: {texto_pedido} (segurança da casa)")
    return Avaliacao(MODERADO, f"pedir à casa: {texto_pedido}")


@ferramenta(
    "casa_falar",
    "Manda um pedido em linguagem natural para o assistente do Home Assistant (Assist), que "
    "entende comandos encadeados: 'apague a luz da sala e ligue o ventilador'.",
    {"texto": texto("O pedido, como o usuário falou")},
    grupo="casa", risco=_risco_falar,
)
def casa_falar(ctx, texto: str):
    url, cabecalho = _ha(ctx)
    resposta = httpx.post(f"{url}/api/conversation/process", headers=cabecalho, timeout=20,
                          json={"text": texto, "language": "pt-BR"})
    resposta.raise_for_status()
    dados = resposta.json()
    fala = (((dados.get("response") or {}).get("speech") or {}).get("plain") or {}).get("speech")
    return {"mensagem": fala or "Pedido enviado ao Home Assistant."}


def sugestoes_da_casa(estados: list[dict]) -> list[str]:
    """Sugestões proativas a partir do estado da casa (sem executar nada sozinho)."""
    sugestoes = []
    temperaturas, umidades = [], []
    luzes_ligadas, abertas = [], []
    ar_ligado = False
    for e in estados:
        ident = e.get("entity_id", "")
        atributos = e.get("attributes", {}) or {}
        nome = atributos.get("friendly_name", ident)
        estado = str(e.get("state", ""))
        classe = atributos.get("device_class", "")
        if ident.startswith("sensor.") and classe == "temperature":
            try:
                temperaturas.append((float(estado), nome))
            except ValueError:
                pass
        if ident.startswith("sensor.") and classe == "humidity":
            try:
                umidades.append((float(estado), nome))
            except ValueError:
                pass
        if ident.startswith("light.") and estado == "on":
            luzes_ligadas.append(nome)
        if ident.startswith("climate.") and estado not in ("off", "unavailable"):
            ar_ligado = True
        if ident.startswith("binary_sensor.") and classe in ("door", "window", "garage_door") \
                and estado == "on":
            abertas.append(nome)
    if temperaturas:
        quente = max(temperaturas)
        if quente[0] >= 28 and not ar_ligado:
            sugestoes.append(f"Está {quente[0]:.0f}°C ({quente[1]}). Quer que eu ligue o ar?")
        frio = min(temperaturas)
        if frio[0] <= 16:
            sugestoes.append(f"Está frio: {frio[0]:.0f}°C ({frio[1]}).")
    if umidades and max(umidades)[0] >= 80:
        sugestoes.append(f"Umidade alta ({max(umidades)[0]:.0f}%). Ligar o desumidificador?")
    if umidades and min(umidades)[0] <= 30:
        sugestoes.append(f"Ar seco ({min(umidades)[0]:.0f}%). Beba água e use o umidificador.")
    hora = time.localtime().tm_hour
    if luzes_ligadas and (hora >= 23 or hora < 6):
        sugestoes.append(f"{len(luzes_ligadas)} luz(es) acesas tarde da noite. Apago?")
    if abertas:
        sugestoes.append("Abertas agora: " + ", ".join(abertas[:5]) + ".")
    return sugestoes


@ferramenta(
    "casa_relatorio",
    "Resumo da casa agora: temperatura, umidade, luzes acesas, portas e janelas abertas, com "
    "sugestões (por exemplo, ligar o ar se estiver quente).",
    grupo="casa",
)
def casa_relatorio(ctx):
    url, cabecalho = _ha(ctx)
    estados = httpx.get(f"{url}/api/states", headers=cabecalho, timeout=15).json()
    resumo = {
        "luzes_acesas": [e.get("attributes", {}).get("friendly_name", e["entity_id"])
                         for e in estados if e["entity_id"].startswith("light.")
                         and e.get("state") == "on"],
        "sensores": [{"nome": a.get("friendly_name", e["entity_id"]),
                      "valor": f"{e.get('state')} {a.get('unit_of_measurement', '')}".strip()}
                     for e in estados if e["entity_id"].startswith("sensor.")
                     and (a := e.get("attributes", {}) or {}).get("device_class")
                     in ("temperature", "humidity")],
    }
    return {**resumo, "sugestoes": sugestoes_da_casa(estados)}


@ferramenta(
    "alexa_anunciar",
    "Faz a Alexa falar um aviso em voz alta (precisa do Alexa Media Player no Home Assistant).",
    {"mensagem": texto("O que a Alexa deve falar"),
     "alexa": texto("Opcional: qual Alexa (ex.: media_player.echo_sala)")},
    grupo="casa", risco=MODERADO, obrigatorios=["mensagem"],
)
def alexa_anunciar(ctx, mensagem: str, alexa: str = ""):
    url, cabecalho = _ha(ctx)
    alvo = alexa or ctx.config.get("casa", "alexa", "") or ""
    if not alvo:
        return {"erro": "Diga qual Alexa usar (ex.: media_player.echo_sala) ou configure "
                        "[casa] alexa no config.toml."}
    resposta = httpx.post(f"{url}/api/services/notify/alexa_media", headers=cabecalho, timeout=15,
                          json={"message": mensagem, "target": [alvo],
                                "data": {"type": "announce"}})
    resposta.raise_for_status()
    return {"mensagem": f"A Alexa ({alvo}) vai falar: {mensagem}"}


_MAC = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


@ferramenta(
    "bluetooth_conectar",
    "Conecta (e pareia, se preciso) um aparelho Bluetooth pelo endereço, ex.: fone ou caixa de "
    "som. Use bluetooth_procurar para achar o endereço.",
    {"endereco": texto("Endereço Bluetooth, ex.: AA:BB:CC:DD:EE:FF")},
    grupo="casa", risco=MODERADO,
)
def bluetooth_conectar(ctx, endereco: str):
    endereco = endereco.strip().upper()
    if not _MAC.match(endereco):
        return {"erro": "Endereço Bluetooth inválido. Use o formato AA:BB:CC:DD:EE:FF."}
    if sistema() == "windows":
        subprocess.Popen(["cmd", "/c", "start", "ms-settings:bluetooth"])  # noqa: S603,S607
        return {"mensagem": "O Windows só pareia aparelhos novos pela tela de Bluetooth. Abri "
                            f"essa tela: escolha o aparelho {endereco}. Depois de pareado, eu "
                            "consigo usar o áudio dele normalmente."}
    if not shutil.which("bluetoothctl"):
        return {"erro": "Não achei o bluetoothctl (pacote bluez) neste sistema."}
    passos = []
    for comando in (["pair", endereco], ["trust", endereco], ["connect", endereco]):
        resultado = subprocess.run(["bluetoothctl", "--timeout", "15", *comando],  # noqa: S603
                                   capture_output=True, text=True, timeout=25, check=False)
        saida = (resultado.stdout + resultado.stderr).strip().splitlines()
        passos.append(f"{comando[0]}: {saida[-1] if saida else resultado.returncode}")
    conectado = any("Connection successful" in p or "connect: Connection successful" in p
                    for p in passos)
    return {"mensagem": ("Conectado a " if conectado else "Tentei conectar a ") + endereco,
            "passos": passos}
