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
import subprocess
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import psutil

from optimus import __version__
from optimus import config as cfg
from optimus.agent import mensagens_para_historico
from optimus.app import Optimus
from optimus.engine.rede import PROVEDORES, MotorRede
from optimus.hardware import resumo
from optimus.safety import interpretar_confirmacao
from optimus.voice import tts
from optimus.network import cloudflare_tunnel

log = logging.getLogger(__name__)
ESTATICOS = Path(__file__).parent / "static"
_SEGREDOS = ("chave_api", "token", "senha", "elevenlabs_chave", "token_comando",
             "token_agenda")


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
        self._motor_cache: tuple[float, bool, list[str]] = (0.0, False, [])
        self._motor_destinos: list[dict[str, Any]] = []
        self._motor_lock = threading.Lock()
        self._motor_atualizando = False
        optimus.iniciar_lembretes(lambda l: self.avisos.append(
            {"tipo": l.get("tipo", "lembrete"), "texto": l["texto"], "quando": time.time()}))
        optimus.iniciar_copiados()

    def _atualizar_motor_status(self) -> None:
        """Consulta o motor fora da thread HTTP: servidores remotos podem não responder."""
        try:
            motor = self.optimus.motor
            disponivel = motor.disponivel()
            modelos = motor.modelos() if disponivel else []
            destinos = motor.estado() if isinstance(motor, MotorRede) else []
            cache = (time.monotonic(), disponivel, modelos, destinos)
        except Exception:
            log.exception("Falha ao consultar disponibilidade do motor de IA")
            cache = (time.monotonic(), False, [], [])
        finally:
            # O cache é atualizado mesmo se o provedor externo falhar.
            with self._motor_lock:
                self._motor_cache = cache[:3]
                self._motor_destinos = cache[3]
                self._motor_atualizando = False

    def motor_status(self) -> tuple[bool, list[str]]:
        """Retorna o último estado imediatamente e atualiza em segundo plano.

        /api/estado é consultado pela interface durante a abertura. Não podemos deixar
        uma chamada HTTP a Ollama/LM Studio/rede segurar a resposta do servidor web.
        """
        agora = time.monotonic()
        with self._motor_lock:
            idade = agora - self._motor_cache[0]
            if idade >= 4.0 and not self._motor_atualizando:
                self._motor_atualizando = True
                threading.Thread(target=self._atualizar_motor_status, daemon=True,
                                 name="status-motor").start()
            return self._motor_cache[1], list(self._motor_cache[2])

    def motor_destinos(self) -> list[dict[str, Any]]:
        """Retorna destinos remotos do cache; nunca sonda a rede na thread HTTP."""
        with self._motor_lock:
            return list(self._motor_destinos)

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
        # Evita que o navegador reutilize app.js antigo após atualização do pacote.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
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

    def _credenciais_validas(self) -> bool:
        if not self.senha:
            return True
        enviada = self.headers.get("X-Optimus-Senha", "")
        cookie = self.headers.get("Cookie", "")
        achado = re.search(r"optimus_senha=([^;]+)", cookie)
        if achado:
            enviada = enviada or achado.group(1)
        return hmac.compare_digest(enviada, self.senha)

    def _exige_senha(self) -> bool:
        """Protege clientes externos, sem pedir senha no navegador do próprio PC.

        cloudflared encaminha a conexão localmente e preserva CF-Ray e
        CF-Connecting-IP. O servidor da porta do celular, por sua vez, sempre
        exige senha, inclusive nos testes e acessos via loopback.
        """
        if not self.senha:
            return False
        if self.server is _servidor_celular:
            return True
        endereco = str(self.client_address[0]) if self.client_address else ""
        if endereco in ("127.0.0.1", "::1"):
            return bool(self.headers.get("CF-Ray") and self.headers.get("CF-Connecting-IP"))
        return True

    def _autorizado(self) -> bool:
        return not self._exige_senha() or self._credenciais_validas()

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
        if caminho.startswith("/v1/"):
            return self._openai(metodo, caminho)
        if metodo == "GET" and not caminho.startswith("/api/"):
            return self._estatico(caminho)
        if caminho == "/api/entrar" and metodo == "POST":
            exige = self._exige_senha()
            ok = not exige or hmac.compare_digest(self._corpo().get("senha", ""), self.senha)
            return self._json({"ok": ok}, 200 if ok else 401)
        if metodo == "GET" and caminho == "/api/agenda.ics":
            return self._agenda(parse_qs(url.query))
        if not self._autorizado():
            return self._json({"erro": "senha necessária"}, 401)
        try:
            if caminho.startswith("/api/estudio/"):
                return self._estudio(metodo, caminho, parse_qs(url.query))
            self._api(metodo, caminho, parse_qs(url.query))
        except Exception as erro:  # noqa: BLE001
            log.exception("Erro na API")
            self._json({"erro": f"{type(erro).__name__}: {erro}"}, 500)

    # API compatível com a da OpenAI (/v1/audio/speech e /v1/audio/transcriptions): outros
    # programas (editores de vídeo, automações) usam as vozes e a transcrição do Optimus.
    def _openai(self, metodo: str, caminho: str) -> None:
        from optimus.web import openai_audio

        bearer = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if self.senha and not (self._autorizado() or hmac.compare_digest(bearer, self.senha)):
            return self._json({"error": {"message": "senha necessária (Bearer)"}}, 401)
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho > 500 * 1024 * 1024:
            return self._json({"error": {"message": "arquivo grande demais"}}, 413)
        corpo = self.rfile.read(tamanho) if tamanho else b""
        status, tipo, dados = openai_audio.atender(
            metodo, caminho, self.headers.get("Content-Type", ""), corpo,
            self.estado.optimus.config)
        self._bytes_status(dados, tipo, status)

    # Tela Estúdio: vozes, narração, clonagem, legendas, dublagem, audiolivro (estudio_api.py)
    def _estudio(self, metodo: str, caminho: str, consulta: dict) -> None:
        from optimus.web import estudio_api

        tamanho = int(self.headers.get("Content-Length") or 0)
        tipo = self.headers.get("Content-Type", "")
        partes = [unquote(p) for p in caminho.strip("/").split("/")[2:]]
        if metodo == "POST" and partes == ["enviar"] and not tipo.startswith("multipart/"):
            # vídeos grandes: vão direto para o disco, em pedaços, sem passar pela memória
            if tamanho > estudio_api.LIMITE_ENVIO:
                return self._json({"erro": "arquivo grande demais (máximo 2 GB)"}, 413)
            nome = unquote(self.headers.get("X-Nome-Arquivo") or "")
            salvo = estudio_api.receber_envio(nome, self.rfile, tamanho)
            return self._json({"caminho": str(salvo)})
        if tamanho > estudio_api.LIMITE_FORMULARIO:
            return self._json({"erro": "pedido grande demais: envie arquivos grandes por "
                                       "/api/estudio/enviar"}, 413)
        corpo = self.rfile.read(tamanho) if tamanho else b""
        status, dados = estudio_api.atender(metodo, partes, consulta, tipo, corpo,
                                            self.estado.optimus)
        if isinstance(dados, Path):
            return self._enviar_arquivo(dados)
        return self._json(dados, status)

    def _enviar_arquivo(self, alvo: Path) -> None:
        """Manda um arquivo em pedaços, com suporte a Range (para o player poder avançar)."""
        total = alvo.stat().st_size
        inicio, fim = 0, total - 1
        faixa = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if faixa and (faixa.group(1) or faixa.group(2)):
            if faixa.group(1):
                inicio = int(faixa.group(1))
                fim = min(int(faixa.group(2)), total - 1) if faixa.group(2) else total - 1
            else:
                inicio = max(0, total - int(faixa.group(2)))
            if inicio > fim:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {inicio}-{fim}/{total}")
        else:
            self.send_response(200)
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fim - inicio + 1))
        nome = alvo.name.encode("ascii", "replace").decode().replace('"', "")
        self.send_header("Content-Disposition", f'inline; filename="{nome}"')
        self.end_headers()
        with open(alvo, "rb") as f:
            f.seek(inicio)
            restante = fim - inicio + 1
            while restante > 0:
                pedaco = f.read(min(1024 * 1024, restante))
                if not pedaco:
                    break
                self.wfile.write(pedaco)
                restante -= len(pedaco)

    def _bytes_status(self, dados: bytes, tipo: str, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _agenda(self, consulta: dict) -> None:
        """Calendário dos lembretes. O app de calendário não manda senha: usa a chave do link."""
        from optimus.web import celular

        optimus = self.estado.optimus
        chave = (consulta.get("chave") or [""])[0]
        token = optimus.config.get("web", "token_agenda", "") or ""
        if not (self._credenciais_validas() or (token and hmac.compare_digest(chave, token))):
            return self._json({"erro": "chave da agenda inválida"}, 401)
        ics = celular.agenda_ics(optimus.banco.lembretes(pendentes=True),
                                 nome=optimus.config.get("geral", "nome") or "Optimus")
        self._bytes(ics.encode("utf-8"), "text/calendar; charset=utf-8")

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

        if recurso == "modulos" and metodo == "GET":
            from optimus import modulos
            return self._json({"modulos": modulos.inventario()})
        if recurso == "modulos" and ident == "recursos" and metodo == "GET":
            from optimus import modulos
            return self._json({"recursos": modulos.recursos()})
        if recurso == "pdf":
            from optimus.tools import pdf as _pdf  # noqa: F401
            from optimus.tools import pdf_suite as _pdf_suite  # noqa: F401
            from optimus.tools.base import Contexto, registradas

            pasta_pdf = (cfg.pasta_base() / "documentos_pdf").resolve()
            pasta_pdf.mkdir(parents=True, exist_ok=True)
            if metodo == "GET" and not ident:
                ferramentas_pdf = [
                    {"nome": f.nome, "descricao": f.descricao,
                     "parametros": f.parametros, "obrigatorios": f.obrigatorios}
                    for f in registradas().values() if f.grupo == "pdf"
                ]
                try:
                    import pypdf  # noqa: F401
                    pdf_instalado = True
                except ImportError:
                    pdf_instalado = False
                return self._json({"ferramentas": ferramentas_pdf,
                                   "pasta": str(pasta_pdf), "dependencias_instaladas": pdf_instalado,
                                   "comando_instalacao": 'pip install "optimus-assistente[pdf]"'})
            if metodo == "POST" and ident == "upload":
                tamanho = int(self.headers.get("Content-Length") or 0)
                if tamanho <= 0 or tamanho > 200 * 1024 * 1024:
                    return self._json({"erro": "Envie um arquivo de até 200 MB."}, 413)
                nome_original = unquote((consulta.get("nome") or ["documento.pdf"])[0])
                nome = re.sub(r"[^\w.() -]", "_", Path(nome_original).name).strip(" .") or "documento.pdf"
                extensao = Path(nome).suffix.lower()
                permitidas = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".html", ".htm", ".p12", ".pfx", ".icc", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv"}
                if extensao not in permitidas:
                    return self._json({"erro": "Tipo de arquivo não suportado. Envie PDF, imagem, documento Office/LibreOffice, HTML, certificado P12/PFX ou perfil ICC."}, 415)
                dados = self.rfile.read(tamanho)
                assinaturas = {
                    ".pdf": dados.startswith(b"%PDF-"),
                    ".jpg": dados.startswith(b"\xff\xd8\xff"),
                    ".jpeg": dados.startswith(b"\xff\xd8\xff"),
                    ".png": dados.startswith(b"\x89PNG\r\n\x1a\n"),
                    ".tif": dados.startswith((b"II*\x00", b"MM\x00*")),
                    ".tiff": dados.startswith((b"II*\x00", b"MM\x00*")),
                    ".bmp": dados.startswith(b"BM"),
                }
                if extensao in assinaturas and not assinaturas[extensao]:
                    return self._json({"erro": "O conteúdo do arquivo não corresponde ao formato informado."}, 415)
                if extensao in {".html", ".htm"} and b"<" not in dados[:4096]:
                    return self._json({"erro": "O arquivo HTML não parece válido."}, 415)
                alvo = pasta_pdf / f"{uuid.uuid4().hex[:8]}_{nome}"
                alvo.write_bytes(dados)
                return self._json({"arquivo": str(alvo), "nome": nome,
                                   "tamanho": len(dados)})
            if metodo == "POST" and ident == "executar":
                corpo = self._corpo()
                nome_ferramenta = str(corpo.get("ferramenta") or "")
                ferramenta_pdf = registradas().get(nome_ferramenta)
                if not ferramenta_pdf or ferramenta_pdf.grupo != "pdf":
                    return self._json({"erro": "Ferramenta PDF inválida."}, 400)
                argumentos = corpo.get("argumentos") or {}
                if not isinstance(argumentos, dict):
                    return self._json({"erro": "Parâmetros inválidos."}, 400)
                # Os arquivos de entrada só podem vir da pasta de documentos enviada pela interface.
                chaves_arquivo = {chave for chave in ferramenta_pdf.parametros
                                  if any(palavra in chave.lower()
                                         for palavra in ("arquivo", "certificado", "perfil_icc"))}
                for chave in chaves_arquivo:
                    valor = argumentos.get(chave)
                    if not valor:
                        continue
                    valores = re.split(r"[,;]+", str(valor)) if chave == "arquivos" or chave.endswith("arquivos") else [str(valor)]
                    for item in valores:
                        item = item.strip().strip('"')
                        if not item:
                            continue
                        caminho = Path(item).expanduser().resolve()
                        if not caminho.is_relative_to(pasta_pdf) or not caminho.is_file():
                            return self._json({"erro": f"Arquivo de entrada não enviado ou fora da pasta segura: {Path(item).name}"}, 400)
                if "destino" in ferramenta_pdf.parametros:
                    destino = str(argumentos.get("destino") or "resultado.pdf")
                    argumentos["destino"] = str(pasta_pdf / Path(destino).name)
                contexto_pdf = Contexto(config=optimus.config, banco=optimus.banco,
                                        pasta_trabalho=pasta_pdf)
                resultado_bruto = ferramenta_pdf.executar(argumentos, contexto_pdf)
                try:
                    resultado = json.loads(resultado_bruto)
                except (TypeError, json.JSONDecodeError):
                    resultado = {"resultado": str(resultado_bruto)}
                if isinstance(resultado, dict) and resultado.get("erro"):
                    return self._json(resultado, 400)
                saidas = []
                if isinstance(resultado, dict):
                    for chave in ("destino", "zip"):
                        valor = resultado.get(chave)
                        if valor:
                            caminho = Path(str(valor)).resolve()
                            if caminho.is_relative_to(pasta_pdf) and caminho.is_file():
                                saidas.append({"nome": caminho.name, "tamanho": caminho.stat().st_size})
                if isinstance(resultado, dict) and resultado.get("arquivos"):
                    for valor in resultado["arquivos"]:
                        caminho = Path(str(valor)).resolve()
                        if caminho.is_relative_to(pasta_pdf) and caminho.is_file():
                            saidas.append({"nome": caminho.name, "tamanho": caminho.stat().st_size})
                return self._json({"resultado": resultado, "arquivos": saidas})
            if metodo == "GET" and ident == "arquivo":
                nome = Path(unquote((consulta.get("nome") or [""])[0])).name
                alvo = (pasta_pdf / nome).resolve()
                if not alvo.is_relative_to(pasta_pdf) or not alvo.is_file():
                    return self._json({"erro": "Arquivo não encontrado."}, 404)
                dados = alvo.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(alvo.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(dados)))
                self.send_header("Content-Disposition", f'attachment; filename="{alvo.name.encode("ascii", "replace").decode()}"')
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(dados)
                return
        if recurso == "estado":
            memoria = psutil.virtual_memory()
            motor = optimus.motor
            disponivel, lista_modelos = estado.motor_status()
            return self._json({
                "versao": __version__,
                "nome": optimus.config.get("geral", "nome"),
                "hardware": optimus.hardware.para_dict(),
                "perfil": optimus.perfil.para_dict(),
                "resumo": resumo(optimus.hardware, optimus.perfil),
                "motor": {"backend": optimus.config.get("motor", "backend"),
                          "disponivel": disponivel, "modelo": optimus.modelo_atual(),
                          "modelos": lista_modelos,
                          "destinos": estado.motor_destinos()},
                "uso": {"cpu": psutil.cpu_percent(interval=None), "ram": memoria.percent,
                        "ram_livre_gb": round(memoria.available / 1024**3, 1)},
                "modo": optimus.config.get("agente", "modo"),
                "avisos": estado.avisos[-10:],
                "aviso_modelo": optimus.aviso_modelo,
                "aviso_atualizacao": getattr(optimus, "aviso_atualizacao", None),
                "so_executar": bool(optimus.config.get("voz", "so_executar", False)),
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
        if recurso == "casa" and ident == "gerenciado":
            from optimus.smart_home import home_assistant as ha

            if metodo == "GET":
                return self._json(ha.estado())
            if metodo == "POST":
                acao = str((self._corpo().get("acao") or "")).strip().lower()
                permitidas = {"instalar", "iniciar", "parar", "reiniciar", "atualizar",
                              "backup", "desinstalar", "logs"}
                if acao not in permitidas:
                    return self._json({"erro": "Ação de gerenciamento inválida."}, 400)
                def executar():
                    try:
                        ha.executar_acao(acao)
                    except Exception:
                        log.exception("Falha no gerenciamento do Home Assistant")
                threading.Thread(target=executar, daemon=True,
                                 name="home-assistant-gerenciado").start()
                return self._json({"ok": True, "mensagem": "Operação iniciada.",
                                   "estado": "executando"}, 202)
        if recurso == "casa" and ident == "testar" and metodo == "POST":
            from urllib.parse import urlsplit
            import httpx

            corpo = self._corpo()
            url = str(corpo.get("url", "")).strip().rstrip("/")
            token = str(corpo.get("token", "")).strip()
            if token == "••••••" or not token:
                token = str(optimus.config.get("casa", "token") or "").strip()
            try:
                partes_url = urlsplit(url)
                if (partes_url.scheme not in ("http", "https") or not partes_url.hostname
                        or partes_url.username or partes_url.password or partes_url.query
                        or partes_url.fragment):
                    return self._json({"ok": False, "erro": "Endereço inválido. Use http://IP:8123 ou https://seu-dominio."}, 400)
                if not token:
                    return self._json({"ok": False, "erro": "Informe o token de acesso de longa duração do Home Assistant."}, 400)
                resposta = httpx.get(
                    f"{url}/api/",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    timeout=8,
                    follow_redirects=False,
                )
                if resposta.status_code == 401:
                    return self._json({"ok": False, "erro": "Token recusado (HTTP 401). Gere um novo token de longa duração no perfil do Home Assistant."}, 401)
                if resposta.status_code == 404:
                    return self._json({"ok": False, "erro": "Endereço não parece ser a API do Home Assistant. Confira IP, porta 8123 e caminho."}, 502)
                resposta.raise_for_status()
                dados = resposta.json()
                if not isinstance(dados, dict) or "message" not in dados:
                    return self._json({"ok": False, "erro": "A resposta não parece ser do Home Assistant."}, 502)
                return self._json({"ok": True, "mensagem": "Conexão autenticada com o Home Assistant.", "api": dados.get("message")})
            except httpx.ConnectError:
                return self._json({"ok": False, "erro": "Não foi possível alcançar esse endereço. Verifique se o Home Assistant está instalado, ligado e na mesma rede; confira o IP e a porta."}, 502)
            except httpx.TimeoutException:
                return self._json({"ok": False, "erro": "O Home Assistant demorou para responder. Confira a rede e tente novamente."}, 504)
            except (httpx.HTTPError, ValueError) as erro:
                log.warning("Teste de conexão Home Assistant falhou: %s", type(erro).__name__)
                return self._json({"ok": False, "erro": "Falha ao validar a API do Home Assistant. Confira endereço, token e conexão."}, 502)
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
        if recurso == "biblioteca":
            from optimus import biblioteca as biblioteca_docs

            if metodo == "GET":
                termo = str((consulta.get("q") or [""])[0]).strip()
                if termo:
                    resultados = biblioteca_docs.buscar(banco, termo, limite=20)
                    return self._json({"consulta": termo, "resultados": resultados,
                                       "total": len(resultados)})
                docs = biblioteca_docs.fontes(banco)
                return self._json({"documentos": docs, "total": len(docs)})
            corpo = self._corpo()
            pasta = corpo.get("pasta", "")
            if not pasta:
                return self._json({"erro": "Informe o caminho da pasta."}, 400)
            alvo = Path(pasta).expanduser()
            if not alvo.is_absolute():
                alvo = Path.home() / alvo
            if metodo == "POST":
                resultado_indexacao = biblioteca_docs.indexar_pasta(
                    banco, alvo, recursivo=bool(corpo.get("recursivo", True)))
                resultado_indexacao["mensagem"] = (
                    f"Indexação: {resultado_indexacao['indexados']} arquivo(s) novo(s)/alterado(s), "
                    f"{resultado_indexacao['trechos']} trecho(s), {resultado_indexacao['removidos']} removido(s), "
                    f"{len(resultado_indexacao['erros'])} erro(s).")
                return self._json(resultado_indexacao)
            removidos = biblioteca_docs.esquecer_pasta(banco, alvo)
            return self._json({"removidos": removidos,
                               "mensagem": f"{removidos} documento(s) removido(s) do conhecimento."})
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
        if recurso == "tunel":
            from optimus.web import celular

            config = optimus.config
            if metodo == "POST" and ident == "desligar":
                parar_tunel()
            elif metodo == "POST":
                senha = str(self._corpo().get("senha", "") or config.get("web", "senha", "")).strip()
                if len(senha) < 12:
                    return self._json({"erro": "Para acesso externo, use uma senha com pelo menos 12 caracteres."}, 400)
                config.definir("web", "senha", senha)
                config.salvar()
                Manipulador.senha = senha
                if _servidor_celular is not None:
                    _servidor_celular.RequestHandlerClass.senha = senha
                resultado = iniciar_tunel(self.server.server_address[1], senha)
                if resultado.get("erro"):
                    return self._json(resultado, 503)
            url_externa = estado_tunel().get("url", "")
            agenda_externa = (f"{url_externa}/api/agenda.ics?chave={celular.token_agenda(config)}"
                              if url_externa else "")
            return self._json({
                **estado_tunel(),
                "qr": celular.qr_svg(url_externa) if url_externa else "",
                "agenda": agenda_externa,
                "agenda_qr": celular.qr_svg(agenda_externa) if agenda_externa else "",
            })
        if recurso == "celular":
            from optimus.web import celular

            host, porta = self.server.server_address[:2]
            rede = host not in ("127.0.0.1", "localhost", "::1")
            config = optimus.config
            if metodo == "POST" and ident == "desligar":
                desligar_celular()
                config.definir("web", "celular", False)
                config.salvar()
            elif metodo == "POST":
                senha = str(self._corpo().get("senha", "") or "").strip()
                if senha:
                    if len(senha) < 4:
                        return self._json({"erro": "A senha precisa ter pelo menos 4 "
                                                   "caracteres."}, 400)
                    config.definir("web", "senha", senha)
                if not config.get("web", "senha", ""):
                    return self._json({"erro": "Crie uma senha para o celular (ela protege o "
                                               "Optimus de outras pessoas da rede)."}, 400)
                try:
                    ligar_celular(optimus, porta_celular(config, porta))
                except OSError as erro:
                    return self._json({"erro": "Não consegui abrir a porta "
                                               f"{porta_celular(config, porta)} na rede: {erro}. "
                                               "Feche outro programa que use essa porta ou mude "
                                               "web.porta_celular."}, 500)
                config.definir("web", "celular", True)
                config.salvar()
                # A senha do acesso móvel e a do túnel compartilham a mesma credencial.
                # Atualiza o handler principal imediatamente após a rotação.
                Manipulador.senha = str(config.get("web", "senha", "") or "")
            if consulta.get("nova_chave"):
                config.definir("web", "token_agenda", "")
            if rede:
                url = celular.endereco_rede(porta, host)
            elif _servidor_celular is not None:
                url = celular.endereco_rede(_servidor_celular.server_address[1])
            else:
                url = celular.endereco_rede(porta, host)
            ligado = rede or _servidor_celular is not None
            agenda = f"{url}/api/agenda.ics?chave={celular.token_agenda(config)}"
            return self._json({
                "url": url, "rede": ligado, "ligado": ligado,
                "tem_senha": bool(config.get("web", "senha", "")),
                "qr": celular.qr_svg(url) if ligado else "",
                "agenda": agenda, "agenda_qr": celular.qr_svg(agenda) if ligado else "",
                "dica": "" if ligado else "O acesso pelo celular está desligado. Crie uma senha "
                                          "e clique em \"Ligar acesso pelo celular\"."})
        if recurso == "atualizacao":
            # Git (clone) ou release do GitHub (instalação sem Git), com SHA-256 e voltar.
            from optimus import autoatualizar

            if metodo == "POST" and ident == "voltar":
                return self._json(autoatualizar.voltar(optimus.config))
            if metodo == "POST":
                return self._json(autoatualizar.baixar(optimus.config))
            return self._json(autoatualizar.verificar(optimus.config))
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
        if recurso == "cameras" and ident == "descobrir" and metodo == "POST":
            from optimus.tools.casa import descobrir_cameras_onvif

            try:
                itens = descobrir_cameras_onvif()
            except OSError as erro:
                log.warning("Descoberta ONVIF falhou: %s", type(erro).__name__)
                return self._json({"erro": "Não foi possível executar a descoberta ONVIF nesta interface de rede."}, 502)
            return self._json({
                "total": len(itens),
                "itens": itens,
                "mensagem": ("Câmeras ONVIF encontradas. Confira os endpoints e informe o link "
                             "RTSP ou snapshot no cadastro da câmera."
                             if itens else "Nenhuma câmera ONVIF respondeu. Confirme se ela está "
                             "na mesma rede e se WS-Discovery está habilitado."),
            })
        if recurso == "cameras" and metodo == "GET":
            from optimus.tools.casa import cameras_configuradas

            return self._json({"cameras": cameras_configuradas(optimus.config)})
        if recurso == "cameras" and metodo == "POST":
            from optimus.tools.casa import montar_url_camera

            corpo = self._corpo()
            url = montar_url_camera(corpo.get("url", ""), corpo.get("usuario", ""),
                                    corpo.get("senha", ""))
            if not url:
                return self._json({"erro": "Informe o link da câmera (rtsp://… ou http://…/snapshot)."},
                                  400)
            cams = list(optimus.config.dados.get("cameras") or [])
            cams.append({"nome": corpo.get("nome", "").strip() or f"Câmera {len(cams) + 1}",
                         "url": url})
            optimus.config.dados["cameras"] = cams
            optimus.config.salvar()
            return self._json({"ok": True})
        if recurso == "cameras" and metodo == "DELETE" and ident.startswith("ip:"):
            try:
                i = int(ident.split(":", 1)[1])
            except ValueError:
                return self._json({"erro": "câmera inválida"}, 400)
            cams = list(optimus.config.dados.get("cameras") or [])
            if 0 <= i < len(cams):
                cams.pop(i)
                optimus.config.dados["cameras"] = cams
                optimus.config.salvar()
                return self._json({"ok": True})
            return self._json({"erro": "câmera não encontrada"}, 404)
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


# ---------------------------------------------------------------------- acesso pelo celular
# Quando a interface roda só neste PC (127.0.0.1), o celular entra por uma segunda porta,
# aberta na rede de casa e sempre protegida pela senha de [web] senha.

_servidor_celular: ThreadingHTTPServer | None = None
_trava_celular = threading.Lock()
def estado_tunel() -> dict[str, str | bool]:
    """Estado reportado pelo gerenciador único do Cloudflare Tunnel."""
    return cloudflare_tunnel.estado()


def iniciar_tunel(porta: int, senha: str) -> dict[str, str | bool]:
    """Instala (com verificação SHA-256) e inicia o Cloudflare Quick Tunnel."""
    return cloudflare_tunnel.iniciar(porta, senha)


def parar_tunel() -> None:
    cloudflare_tunnel.parar()


def porta_celular(config, porta_principal: int) -> int:
    return int(config.get("web", "porta_celular", 0) or (int(porta_principal) + 1))


def ligar_celular(optimus: Optimus, porta: int) -> ThreadingHTTPServer:
    global _servidor_celular
    senha = optimus.config.get("web", "senha", "") or ""
    if not senha:
        raise ValueError("defina uma senha antes de abrir para a rede")
    with _trava_celular:
        if _servidor_celular is not None:
            _servidor_celular.RequestHandlerClass.senha = senha  # senha nova vale na hora
            return _servidor_celular
        manipulador = type("ManipuladorCelular", (Manipulador,), {"senha": senha})
        servidor = ThreadingHTTPServer(("0.0.0.0", porta), manipulador)
        servidor.daemon_threads = True
        threading.Thread(target=servidor.serve_forever, daemon=True,
                         name="optimus-celular").start()
        _servidor_celular = servidor
        return servidor


def desligar_celular() -> None:
    global _servidor_celular
    with _trava_celular:
        if _servidor_celular is not None:
            _servidor_celular.shutdown()
            _servidor_celular.server_close()
            _servidor_celular = None


def _senha_para_acesso(senha: str, host: str, tunel: bool) -> str:
    """Exige senha apenas quando a interface é exposta à rede ou por túnel."""
    if host in ("127.0.0.1", "localhost", "::1") and not tunel:
        return ""
    return senha


def iniciar(host: str = "127.0.0.1", porta: int = 8765, abrir_navegador: bool = True,
            optimus: Optimus | None = None, tunel: bool = False) -> None:
    global _porta_principal
    optimus = optimus or Optimus()
    senha = optimus.config.get("web", "senha") or ""
    if tunel and len(senha) < 12:
        raise SystemExit("Para usar --tunel, defina uma senha forte com pelo menos 12 caracteres: "
                         "optimus config web.senha SUA_SENHA_FORTE")
    if host not in ("127.0.0.1", "localhost") and not senha:
        raise SystemExit("Para abrir a interface na rede (celular), defina uma senha: "
                         "optimus config web.senha SUA_SENHA")
    Manipulador.estado = Estado(optimus)
    threading.Thread(target=aquecer_modelos, args=(optimus,), daemon=True).start()
    # A senha protege o acesso de outros aparelhos; só neste PC (127.0.0.1) não é pedida.
    # A senha da rede/túnel não deve bloquear o próprio usuário no acesso local.
    # Ela só é exigida quando a interface é exposta na rede ou por um túnel.
    Manipulador.senha = _senha_para_acesso(senha, host, tunel)
    servidor = ThreadingHTTPServer((host, porta), Manipulador)
    _porta_principal = servidor.server_address[1]
    servidor.daemon_threads = True
    if tunel:
        resultado = iniciar_tunel(servidor.server_address[1], senha)
        if resultado.get("erro"):
            parar_tunel()
            servidor.server_close()
            raise SystemExit(str(resultado["erro"]))
        print(f"Acesso externo: {resultado.get('url') or 'túnel iniciando; consulte o painel'}")
    try:  # pastas observadas do estúdio passam a rodar enquanto a interface estiver aberta
        from optimus.estudio import automacao

        automacao.iniciar_se_preciso(optimus.config)
    except Exception:  # noqa: BLE001
        pass
    endereco = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{porta}"
    print(f"Optimus {__version__} rodando em {endereco}  (Ctrl+C para parar)")
    if host not in ("127.0.0.1", "localhost"):
        from optimus.web import celular

        no_celular = celular.endereco_rede(porta, host)
        print(f"No celular (mesma rede Wi-Fi): {no_celular}")
        celular.qr_terminal(no_celular)
    elif optimus.config.get("web", "celular", False) and senha:
        try:
            ligar_celular(optimus, porta_celular(optimus.config, porta))
            from optimus.web import celular

            print("No celular (mesma rede Wi-Fi): "
                  + celular.endereco_rede(porta_celular(optimus.config, porta)))
        except OSError as erro:
            print(f"Acesso pelo celular não abriu: {erro}")
    if abrir_navegador:
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nAté logo!")
    finally:
        parar_tunel()
        servidor.server_close()
        _porta_principal = None


__all__ = ["iniciar", "cfg", "iniciar_tunel", "parar_tunel", "estado_tunel"]
