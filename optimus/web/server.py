"""Interface visual: servidor local (só biblioteca padrão do Python) + página web.

Abre em http://127.0.0.1:8765. Para usar pelo celular na mesma rede, inicie com
`optimus gui --rede` e defina uma senha em [web] senha.
"""

from __future__ import annotations

import hmac
import json
import logging
import mimetypes
import queue
import re
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import psutil

from optimus import __version__
from optimus import config as cfg
from optimus.agent import mensagens_para_historico
from optimus.app import Optimus
from optimus.engine.rede import PROVEDORES, MotorRede
from optimus.hardware import resumo
from optimus.safety import interpretar_confirmacao
from optimus.voice import tts

log = logging.getLogger(__name__)
ESTATICOS = Path(__file__).parent / "static"
_SEGREDOS = ("chave_api", "token", "senha", "elevenlabs_chave", "token_comando")


class Tarefa:
    """Um pedido em andamento: pendente → executando → concluida / falhou / cancelada."""

    def __init__(self):
        self.id = uuid.uuid4().hex[:12]
        self.eventos: list[dict[str, Any]] = []
        self.estado = "pendente"
        self.pendente: dict[str, Any] | None = None
        self._resposta: queue.Queue[bool] = queue.Queue()
        self._cancelar = threading.Event()
        self._contador = 0
        self.criada = time.time()

    @property
    def terminou(self) -> bool:
        return self.estado in ("concluida", "falhou", "cancelada")

    def evento(self, dados: dict[str, Any]) -> None:
        dados["quando"] = time.time()
        self.eventos.append(dados)

    def confirmar(self, chamada, avaliacao) -> bool:
        self._contador += 1
        self.pendente = {"id": f"{self.id}-{self._contador}", "nome": chamada.nome,
                         "argumentos": chamada.argumentos, "motivo": avaliacao.motivo,
                         "nivel": avaliacao.nivel}
        aprovado = False
        limite = time.monotonic() + 600
        while time.monotonic() < limite and not self._cancelar.is_set():
            try:
                aprovado = self._resposta.get(timeout=0.5)
                break
            except queue.Empty:
                continue
        self.pendente = None
        return aprovado

    def responder(self, aprovado: bool) -> None:
        self._resposta.put(aprovado)

    def cancelar(self) -> None:
        self._cancelar.set()

    def cancelada(self) -> bool:
        return self._cancelar.is_set()


class Estado:
    def __init__(self, optimus: Optimus):
        self.optimus = optimus
        self.tarefas: dict[str, Tarefa] = {}
        self.avisos: list[dict[str, Any]] = []
        self.downloads: dict[str, dict[str, Any]] = {}
        self._falantes: dict[str, tts.Falante] = {}
        self._ouvinte = None
        optimus.iniciar_lembretes(lambda l: self.avisos.append(
            {"tipo": "lembrete", "texto": l["texto"], "quando": time.time()}))

    def falante(self, voz: str) -> tts.Falante:
        if voz not in self._falantes:
            self._falantes[voz] = tts.Falante(
                voz, self.optimus.config.get("voz", "velocidade", 1.0),
                config=self.optimus.config)
        return self._falantes[voz]

    def ouvinte(self):
        if self._ouvinte is None:
            from optimus.voice.stt import Ouvinte

            self._ouvinte = Ouvinte(self.optimus.config.get("voz", "modelo_stt")
                                    or self.optimus.perfil.modelo_stt)
        return self._ouvinte

    def limpar(self) -> None:
        limite = time.time() - 3600
        for chave in [k for k, t in list(self.tarefas.items())
                      if t.terminou and t.criada < limite]:
            del self.tarefas[chave]


_SENHA_EM_LINK = re.compile(r"(://[^:/@\s]+:)[^@\s]+@")


def _mascarar_config(dados: dict) -> dict:
    copia = json.loads(json.dumps(dados))
    for secao in copia.values():
        for item in (secao if isinstance(secao, list) else [secao]):
            if isinstance(item, dict):
                for chave, valor in item.items():
                    if isinstance(valor, str):
                        item[chave] = _SENHA_EM_LINK.sub(r"\1••••••@", valor)
    for secao in copia.values():
        itens = secao if isinstance(secao, list) else [secao]
        for item in itens:
            if isinstance(item, dict):
                for chave in _SEGREDOS:
                    if item.get(chave):
                        item[chave] = "••••••"
    return copia


_MODOS = {
    "web": "Pesquise na internet sobre ",
    "imagem": "Gere uma imagem de ",
}


def _aplicar_modo(texto: str, modo: str) -> str:
    """Os botões de modo da interface (pesquisar, gerar imagem) viram parte do pedido."""
    prefixo = _MODOS.get(modo, "")
    return prefixo + texto if prefixo and not texto.lower().startswith(prefixo[:12].lower()) \
        else texto


def _executar_pedido(estado: Estado, tarefa: Tarefa, corpo: dict[str, Any]) -> None:
    optimus = estado.optimus
    banco = optimus.banco
    tarefa.estado = "executando"
    try:
        conversa_id = int(corpo.get("conversa") or 0)
        texto = str(corpo.get("texto", "")).strip()
        if not conversa_id:
            conversa_id = banco.nova_conversa(projeto=corpo.get("projeto", ""),
                                              persona=corpo.get("persona") or "optimus")
            tarefa.evento({"tipo": "conversa", "id": conversa_id})
        conversa = banco.conversa(conversa_id) or {}
        historico = mensagens_para_historico(banco.mensagens(conversa_id, limite=40))
        if not historico:
            banco.atualizar_conversa(conversa_id, titulo=(texto[:48] + ("…" if len(texto) > 48
                                                                          else "")))
        banco.adicionar_mensagem(conversa_id, "user", texto)
        participantes = corpo.get("grupo") or [corpo.get("persona") or conversa.get("persona")
                                               or "optimus"]
        if corpo.get("modo") == "programar" and not corpo.get("grupo") and \
                banco.persona("programador"):
            participantes = ["programador"]
        for chave in participantes[:5]:
            persona = banco.persona(chave) or banco.persona("optimus")
            if tarefa.cancelada():
                break
            agente = optimus.criar_agente(confirmar=tarefa.confirmar, ao_evento=tarefa.evento)
            agente.cancelado = tarefa.cancelada
            modo = corpo.get("modo") or ""
            if modo == "pensar":
                agente.pensar = True
            pedido = _aplicar_modo(texto, modo)
            if len(participantes) > 1:
                pedido = (f"{texto}\n\n(Conversa em grupo. Você é {persona['nome']}. Responda do "
                          "seu ponto de vista, sem repetir o que os outros já disseram.)")
            inicio = time.time()
            resposta = agente.responder(pedido, historico, persona=persona,
                                        por_voz=bool(corpo.get("voz")))
            extra = {"persona": persona["chave"], "nome": persona["nome"],
                     "segundos": round(time.time() - inicio, 1)}
            banco.adicionar_mensagem(conversa_id, "assistant", resposta, extra)
            historico += [{"role": "user", "content": pedido},
                          {"role": "assistant", "content": f"[{persona['nome']}] {resposta}"}]
            tarefa.evento({"tipo": "final", "texto": resposta, **extra})
        tarefa.estado = "cancelada" if tarefa.cancelada() else "concluida"
    except Exception as erro:  # noqa: BLE001 - o erro vai para a tela, não some
        log.exception("Falha no pedido")
        tarefa.evento({"tipo": "erro", "texto": f"{type(erro).__name__}: {erro}"})
        tarefa.estado = "falhou"


def _baixar_modelo(estado: Estado, modelo: str) -> None:
    info = estado.downloads[modelo]

    def progresso(dados):
        if dados.get("total"):
            info["pct"] = round(100 * dados.get("completed", 0) / dados["total"], 1)
        info["status"] = dados.get("status", "")

    ok = estado.optimus.motor.baixar(modelo, progresso)
    info.update({"terminou": True, "ok": ok, "pct": 100 if ok else info.get("pct", 0)})


class Manipulador(BaseHTTPRequestHandler):
    estado: Estado
    senha: str = ""
    server_version = f"Optimus/{__version__}"

    def log_message(self, formato, *args):  # silencioso
        log.debug(formato, *args)

    # Respostas
    def _json(self, dados: Any, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _bytes(self, dados: bytes, tipo: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _corpo(self) -> dict[str, Any]:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not tamanho:
            return {}
        try:
            return json.loads(self.rfile.read(tamanho))
        except json.JSONDecodeError:
            return {}

    def _autorizado(self) -> bool:
        if not self.senha:
            return True
        enviada = self.headers.get("X-Optimus-Senha", "")
        cookie = self.headers.get("Cookie", "")
        achado = re.search(r"optimus_senha=([^;]+)", cookie)
        if achado:
            enviada = enviada or achado.group(1)
        return hmac.compare_digest(enviada, self.senha)

    # Roteamento
    def do_GET(self):
        self._rotear("GET")

    def do_POST(self):
        self._rotear("POST")

    def do_DELETE(self):
        self._rotear("DELETE")

    def _rotear(self, metodo: str) -> None:
        url = urlparse(self.path)
        caminho = url.path
        if metodo == "GET" and not caminho.startswith("/api/"):
            return self._estatico(caminho)
        if caminho == "/api/entrar" and metodo == "POST":
            ok = not self.senha or hmac.compare_digest(self._corpo().get("senha", ""), self.senha)
            return self._json({"ok": ok}, 200 if ok else 401)
        if not self._autorizado():
            return self._json({"erro": "senha necessária"}, 401)
        try:
            self._api(metodo, caminho, parse_qs(url.query))
        except Exception as erro:  # noqa: BLE001
            log.exception("Erro na API")
            self._json({"erro": f"{type(erro).__name__}: {erro}"}, 500)

    def _estatico(self, caminho: str) -> None:
        if caminho in ("/", ""):
            caminho = "/index.html"
        alvo = (ESTATICOS / caminho.lstrip("/")).resolve()
        if not str(alvo).startswith(str(ESTATICOS.resolve())) or not alvo.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript",):
            tipo += "; charset=utf-8"
        self._bytes(alvo.read_bytes(), tipo)

    def _api(self, metodo: str, caminho: str, consulta: dict) -> None:
        estado = self.estado
        optimus = estado.optimus
        banco = optimus.banco
        partes = caminho.strip("/").split("/")[1:]
        recurso = partes[0] if partes else ""
        ident = partes[1] if len(partes) > 1 else ""

        if recurso == "estado":
            memoria = psutil.virtual_memory()
            motor = optimus.motor
            disponivel = motor.disponivel()
            return self._json({
                "versao": __version__,
                "nome": optimus.config.get("geral", "nome"),
                "hardware": optimus.hardware.para_dict(),
                "perfil": optimus.perfil.para_dict(),
                "resumo": resumo(optimus.hardware, optimus.perfil),
                "motor": {"backend": optimus.config.get("motor", "backend"),
                          "disponivel": disponivel, "modelo": optimus.modelo_atual(),
                          "modelos": motor.modelos() if disponivel else [],
                          "destinos": motor.estado() if isinstance(motor, MotorRede) else []},
                "uso": {"cpu": psutil.cpu_percent(interval=None), "ram": memoria.percent,
                        "ram_livre_gb": round(memoria.available / 1024**3, 1)},
                "modo": optimus.config.get("agente", "modo"),
                "avisos": estado.avisos[-10:],
                "aviso_modelo": optimus.aviso_modelo,
            })
        if recurso == "conversas":
            if metodo == "GET" and not ident:
                return self._json({"conversas": banco.conversas(), "projetos": banco.projetos()})
            if metodo == "GET" and len(partes) > 2 and partes[2] == "mensagens":
                return self._json({"conversa": banco.conversa(int(ident)),
                                   "mensagens": banco.mensagens(int(ident))})
            if metodo == "POST" and not ident:
                corpo = self._corpo()
                return self._json({"id": banco.nova_conversa(
                    projeto=corpo.get("projeto", ""), persona=corpo.get("persona", "optimus"))})
            if metodo == "POST" and ident:
                banco.atualizar_conversa(int(ident), **self._corpo())
                return self._json({"ok": True})
            if metodo == "DELETE":
                banco.apagar_conversa(int(ident))
                return self._json({"ok": True})
        if recurso == "enviar" and metodo == "POST":
            estado.limpar()
            tarefa = Tarefa()
            estado.tarefas[tarefa.id] = tarefa
            threading.Thread(target=_executar_pedido, args=(estado, tarefa, self._corpo()),
                             daemon=True).start()
            return self._json({"tarefa": tarefa.id})
        if recurso == "tarefa" and ident in estado.tarefas:
            tarefa = estado.tarefas[ident]
            desde = int((consulta.get("desde") or ["0"])[0])
            return self._json({"eventos": tarefa.eventos[desde:], "total": len(tarefa.eventos),
                               "pendente": tarefa.pendente, "terminou": tarefa.terminou,
                               "estado": tarefa.estado})
        if recurso == "cancelar" and metodo == "POST":
            tarefa = estado.tarefas.get(self._corpo().get("tarefa", ""))
            if tarefa:
                tarefa.cancelar()
            return self._json({"ok": bool(tarefa)})
        if recurso == "confirmar" and metodo == "POST":
            corpo = self._corpo()
            tarefa = estado.tarefas.get(corpo.get("tarefa", ""))
            if not tarefa:
                return self._json({"erro": "tarefa não encontrada"}, 404)
            if not tarefa.pendente:
                return self._json({"erro": "não há confirmação pendente nesta tarefa"}, 409)
            if corpo.get("id") and corpo["id"] != tarefa.pendente.get("id"):
                return self._json({"erro": "esta confirmação já foi respondida"}, 409)
            aprovado = corpo.get("aprovar")
            if isinstance(aprovado, str):
                nivel = (tarefa.pendente or {}).get("nivel", 1)
                aprovado = interpretar_confirmacao(aprovado, nivel)
            tarefa.responder(bool(aprovado))
            return self._json({"ok": True, "aprovado": bool(aprovado)})
        if recurso == "config":
            if metodo == "GET":
                return self._json({"config": _mascarar_config(optimus.config.dados),
                                   "caminho": str(optimus.config.caminho),
                                   "provedores": PROVEDORES})
            corpo = self._corpo()
            for secao, valores in corpo.items():
                if isinstance(valores, list):
                    antigos = optimus.config.dados.get(secao) or []
                    for i, item in enumerate(valores):
                        for chave in _SEGREDOS:
                            if item.get(chave) == "••••••" and i < len(antigos):
                                item[chave] = antigos[i].get(chave, "")
                    optimus.config.dados[secao] = valores
                    continue
                for chave, valor in (valores or {}).items():
                    if isinstance(valor, str) and "••••••" in valor:  # mascarado na tela: mantém
                        continue
                    optimus.config.definir(secao, chave, valor)
            optimus.config.salvar()
            optimus.recarregar()
            estado._falantes.clear()
            return self._json({"ok": True})
        if recurso == "personas":
            if metodo == "GET":
                return self._json({"personas": banco.personas()})
            if metodo == "POST":
                p = self._corpo()
                chave = p.get("chave") or re.sub(r"[^a-z0-9]+", "-", p.get("nome", "").lower())
                banco.salvar_persona(chave.strip("-") or uuid.uuid4().hex[:6], p.get("nome", ""),
                                     p.get("prompt", ""), p.get("descricao", ""),
                                     p.get("modelo", ""), p.get("voz", ""))
                return self._json({"ok": True})
            banco.apagar_persona(ident)
            return self._json({"ok": True})
        if recurso == "prompts":
            if metodo == "GET":
                return self._json({"prompts": banco.prompts()})
            if metodo == "POST":
                p = self._corpo()
                return self._json({"id": banco.salvar_prompt(p.get("titulo", ""),
                                                             p.get("texto", ""),
                                                             p.get("categoria", "Geral"))})
            banco.apagar_prompt(int(ident))
            return self._json({"ok": True})
        if recurso == "memoria":
            if metodo == "GET":
                return self._json({"fatos": banco.fatos()})
            if metodo == "POST":
                banco.lembrar_fato(self._corpo().get("texto", ""))
                return self._json({"ok": True})
            banco.esquecer_fato(int(ident))
            return self._json({"ok": True})
        if recurso == "conhecimento":
            if metodo == "GET":
                return self._json({"fontes": banco.fontes()})
            banco.esquecer_fonte((consulta.get("fonte") or [""])[0])
            return self._json({"ok": True})
        if recurso == "lembretes":
            if metodo == "GET":
                return self._json({"lembretes": banco.lembretes()})
            banco.apagar_lembrete(int(ident))
            return self._json({"ok": True})
        if recurso == "acoes":
            return self._json({"acoes": optimus.auditoria.ultimas(100)})
        if recurso == "vozes":
            chave = optimus.config.get("voz", "elevenlabs_chave", "")
            return self._json({
                "vozes": [dict(v.__dict__, disponivel=tts.voz_disponivel(v, True, chave))
                          for v in tts.VOZES],
                "kokoro": tts.kokoro_instalado(), "edge": tts.edge_instalado(),
                "atual": tts.escolher_voz(optimus.config.get("voz", "voz"),
                                          chave_elevenlabs=chave).__dict__})
        if recurso == "falar" and metodo == "POST":
            # Uma frase (ou um trecho) por vez: a interface pede frase por frase e toca em
            # sequência, então a fala começa logo e a resposta inteira é falada.
            corpo = self._corpo()
            falante = estado.falante(corpo.get("voz") or optimus.config.get("voz", "voz"))
            frases = tts.dividir_frases(corpo.get("texto", ""))
            if not frases:
                return self._json({"erro": "nada para falar"}, 400)
            try:
                audio, formato = falante.sintetizar(" ".join(frases)[:4000])
            except Exception as erro:  # noqa: BLE001 - a interface usa a voz do navegador
                log.warning("Fala falhou: %s", erro)
                return self._json({"erro": f"{type(erro).__name__}: {erro}",
                                   "voz": falante.voz.nome}, 503)
            if not audio:
                return self._json({"erro": "o motor de voz não gerou áudio"}, 503)
            return self._bytes(audio, "audio/mpeg" if formato == "mp3" else "audio/wav")
        if recurso == "ouvir" and metodo == "POST":
            tamanho = int(self.headers.get("Content-Length") or 0)
            audio = self.rfile.read(tamanho)
            try:
                texto = estado.ouvinte().transcrever(audio)
            except ImportError:
                return self._json({"erro": "O reconhecimento offline (faster-whisper) não está "
                                           "instalado: pip install faster-whisper"}, 503)
            except Exception as erro:  # noqa: BLE001
                log.warning("Reconhecimento falhou: %s", erro)
                return self._json({"erro": f"{type(erro).__name__}: {erro}"}, 503)
            return self._json({"texto": texto})
        if recurso == "cameras" and metodo == "GET":
            from optimus.tools.casa import cameras_configuradas

            return self._json({"cameras": cameras_configuradas(optimus.config)})
        if recurso == "camera" and metodo == "GET":
            from optimus.tools.casa import cameras_configuradas, imagem_da_camera

            ident_camera = (consulta.get("id") or [""])[0]
            # Só câmeras conhecidas: a interface não vira um proxy para qualquer endereço.
            if ident_camera not in {c["id"] for c in cameras_configuradas(optimus.config)}:
                return self._json({"erro": "câmera desconhecida"}, 404)
            try:
                foto = imagem_da_camera(optimus.config, ident_camera)
                return self._bytes(foto, "image/png" if foto[:4] == b"\x89PNG" else "image/jpeg")
            except Exception as erro:  # noqa: BLE001
                return self._json({"erro": f"{type(erro).__name__}: {erro}"}, 502)
        if recurso == "midia" and metodo == "GET" and len(partes) == 3:
            pasta, nome = partes[1], partes[2]
            if pasta not in ("imagens", "cameras") or "/" in nome or ".." in nome:
                return self._json({"erro": "arquivo não permitido"}, 403)
            alvo = cfg.pasta_base() / pasta / nome
            if not alvo.is_file():
                return self._json({"erro": "não encontrado"}, 404)
            tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
            return self._bytes(alvo.read_bytes(), tipo)
        if recurso == "modelos" and ident == "baixar" and metodo == "POST":
            modelo = self._corpo().get("modelo", "")
            if modelo and estado.downloads.get(modelo, {}).get("terminou") is not False:
                estado.downloads[modelo] = {"pct": 0, "terminou": False}
                threading.Thread(target=_baixar_modelo, args=(estado, modelo),
                                 daemon=True).start()
            return self._json({"ok": True})
        if recurso == "modelos" and ident == "catalogo":
            from optimus import modelos

            memoria, gpu = modelos.memoria_util_gb(optimus.hardware)
            return self._json({"memoria_util_gb": memoria, "gpu": gpu,
                               "familias": modelos.melhores_por_familia(optimus.hardware),
                               "catalogo": [m.para_dict() for m in modelos.CATALOGO]})
        if recurso == "modelo" and ident in ("atualizar", "dispensar") and metodo == "POST":
            from optimus import modelos

            aviso = optimus.aviso_modelo
            if not aviso:
                return self._json({"erro": "não há troca de modelo pendente"}, 409)
            if ident == "dispensar":
                modelos.dispensar_aviso(optimus.config, optimus.hardware)
            else:
                modelos.aceitar_upgrade(optimus.config, optimus.hardware, aviso["modelo"])
                if estado.downloads.get(aviso["modelo"], {}).get("terminou") is not False:
                    estado.downloads[aviso["modelo"]] = {"pct": 0, "terminou": False}
                    threading.Thread(target=_baixar_modelo, args=(estado, aviso["modelo"]),
                                     daemon=True).start()
                optimus.recarregar()
            optimus.aviso_modelo = None
            return self._json({"ok": True, "modelo": aviso["modelo"]})
        if recurso == "modelos" and ident == "progresso":
            return self._json(estado.downloads)
        self._json({"erro": "rota não encontrada"}, 404)


def aquecer_modelos(optimus: Optimus) -> list[str]:
    """Deixa o modelo rápido (voz) e o principal carregados: a 1ª resposta não espera o disco."""
    motor = optimus.motor
    alvos = getattr(motor, "destinos", None)
    motores = [d.motor for d in alvos] if alvos else [motor]
    manter = optimus.config.get("motor", "manter_carregado", "30m") or "30m"
    modelos = []
    for nome in (optimus.config.get("motor", "modelo_rapido") or optimus.perfil.modelo_rapido,
                 optimus.modelo_atual()):
        if nome and nome not in modelos:
            modelos.append(nome)
    aquecidos = []
    for m in motores:
        if not hasattr(m, "aquecer"):
            continue
        for nome in modelos:
            if m.aquecer(nome, manter):
                aquecidos.append(nome)
    return aquecidos


def iniciar(host: str = "127.0.0.1", porta: int = 8765, abrir_navegador: bool = True,
            optimus: Optimus | None = None) -> None:
    optimus = optimus or Optimus()
    senha = optimus.config.get("web", "senha") or ""
    if host not in ("127.0.0.1", "localhost") and not senha:
        raise SystemExit("Para abrir a interface na rede (celular), defina uma senha: "
                         "optimus config web.senha SUA_SENHA")
    Manipulador.estado = Estado(optimus)
    threading.Thread(target=aquecer_modelos, args=(optimus,), daemon=True).start()
    Manipulador.senha = senha
    servidor = ThreadingHTTPServer((host, porta), Manipulador)
    servidor.daemon_threads = True
    endereco = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{porta}"
    print(f"Optimus {__version__} rodando em {endereco}  (Ctrl+C para parar)")
    if abrir_navegador:
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nAté logo!")
    finally:
        servidor.server_close()


__all__ = ["iniciar", "cfg"]
