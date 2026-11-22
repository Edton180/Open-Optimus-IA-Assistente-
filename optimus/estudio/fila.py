"""Fila de tarefas longas do estúdio (dublagem, legendas, transcrição, lote).

Roda uma tarefa por vez numa linha de execução própria, com progresso, cancelar e repetir.
As tarefas terminadas ficam registradas em `estudio/fila.json`.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from optimus.estudio import pasta_estudio

log = logging.getLogger(__name__)


@dataclass
class Tarefa:
    id: str
    tipo: str
    titulo: str
    argumentos: dict = field(default_factory=dict)
    estado: str = "na_fila"  # na_fila | rodando | concluida | falhou | cancelada
    progresso: float = 0.0
    mensagem: str = "Aguardando"
    resultado: dict = field(default_factory=dict)
    erro: str = ""
    criada: float = field(default_factory=time.time)
    terminada: float = 0.0

    @property
    def terminou(self) -> bool:
        return self.estado in ("concluida", "falhou", "cancelada")

    def para_dict(self) -> dict:
        d = asdict(self)
        d["argumentos"] = {k: v for k, v in self.argumentos.items() if not k.startswith("_")}
        d["progresso"] = round(self.progresso, 3)
        return d


Trabalho = Callable[..., dict]


class Fila:
    def __init__(self):
        self.tarefas: dict[str, Tarefa] = {}
        self._trabalhos: dict[str, Trabalho] = {}
        self._cancelar: dict[str, threading.Event] = {}
        self._pendentes: list[str] = []
        self._trava = threading.Lock()
        self._acordar = threading.Event()
        self._linha: threading.Thread | None = None
        self._carregar()

    # ------------------------------------------------------------------ registro
    def _arquivo(self):
        return pasta_estudio() / "fila.json"

    def _carregar(self) -> None:
        try:
            for d in json.loads(self._arquivo().read_text(encoding="utf-8")):
                t = Tarefa(**{k: v for k, v in d.items() if k in Tarefa.__dataclass_fields__})
                if not t.terminou:  # o Optimus fechou no meio: marca como interrompida
                    t.estado, t.erro = "falhou", "Interrompida (o Optimus foi fechado)."
                self.tarefas[t.id] = t
        except (OSError, ValueError, TypeError):
            pass

    def _gravar(self) -> None:
        try:
            arq = self._arquivo()
            arq.parent.mkdir(parents=True, exist_ok=True)
            itens = sorted(self.tarefas.values(), key=lambda t: t.criada)[-200:]
            arq.write_text(json.dumps([t.para_dict() for t in itens], ensure_ascii=False,
                                      indent=1), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ uso
    def adicionar(self, tipo: str, titulo: str, trabalho: Trabalho, **argumentos) -> Tarefa:
        t = Tarefa(uuid.uuid4().hex[:10], tipo, titulo, argumentos)
        with self._trava:
            self.tarefas[t.id] = t
            self._trabalhos[t.id] = trabalho
            self._cancelar[t.id] = threading.Event()
            self._pendentes.append(t.id)
        self._gravar()
        self._iniciar()
        return t

    def obter(self, tarefa_id: str) -> Tarefa | None:
        return self.tarefas.get(tarefa_id)

    def listar(self, limite: int = 30) -> list[Tarefa]:
        return sorted(self.tarefas.values(), key=lambda t: t.criada, reverse=True)[:limite]

    def cancelar(self, tarefa_id: str) -> bool:
        t = self.tarefas.get(tarefa_id)
        if not t or t.terminou:
            return False
        evento = self._cancelar.get(tarefa_id)
        if evento:
            evento.set()
        with self._trava:
            if tarefa_id in self._pendentes:
                self._pendentes.remove(tarefa_id)
                t.estado, t.mensagem, t.terminada = "cancelada", "Cancelada", time.time()
        self._gravar()
        return True

    def repetir(self, tarefa_id: str) -> Tarefa | None:
        t = self.tarefas.get(tarefa_id)
        trabalho = self._trabalhos.get(tarefa_id)
        if not t or not t.terminou or not trabalho:
            return None
        return self.adicionar(t.tipo, t.titulo, trabalho, **t.argumentos)

    def esperar(self, tarefa_id: str, limite: float = 3600) -> Tarefa | None:
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            t = self.tarefas.get(tarefa_id)
            if not t or t.terminou:
                return t
            time.sleep(0.05)
        return self.tarefas.get(tarefa_id)

    # ------------------------------------------------------------------ execução
    def _iniciar(self) -> None:
        with self._trava:
            self._acordar.set()
            if self._linha is not None:
                return
            self._linha = threading.Thread(target=self._rodar, daemon=True,
                                           name="estudio-fila")
            self._linha.start()

    def _rodar(self) -> None:
        while True:
            with self._trava:
                proxima = self._pendentes.pop(0) if self._pendentes else None
                if proxima is None:
                    self._acordar.clear()
            if proxima is not None:
                self._executar(proxima)
                continue
            if self._acordar.wait(30):
                continue
            with self._trava:  # ociosa: encerra (uma nova começa no próximo pedido)
                if not self._pendentes:
                    self._linha = None
                    return

    def _executar(self, tarefa_id: str) -> None:
        t = self.tarefas[tarefa_id]
        evento = self._cancelar[tarefa_id]
        t.estado, t.mensagem = "rodando", "Começando"
        self._gravar()

        def progresso(valor: float, mensagem: str = "") -> None:
            t.progresso = max(0.0, min(1.0, float(valor)))
            if mensagem:
                t.mensagem = mensagem

        try:
            resultado: Any = self._trabalhos[tarefa_id](progresso=progresso,
                                                         cancelado=evento.is_set,
                                                         **t.argumentos)
            if evento.is_set():
                t.estado, t.mensagem = "cancelada", "Cancelada"
            else:
                t.estado, t.progresso, t.mensagem = "concluida", 1.0, "Pronto!"
                t.resultado = resultado if isinstance(resultado, dict) else {"valor": resultado}
        except Exception as erro:  # noqa: BLE001 - a fila nunca morre por uma tarefa
            if evento.is_set():
                t.estado, t.mensagem = "cancelada", "Cancelada"
            else:
                t.estado, t.erro = "falhou", str(erro) or type(erro).__name__
                t.mensagem = "Falhou"
                log.info("Tarefa %s falhou: %s", tarefa_id, traceback.format_exc())
        t.terminada = time.time()
        self._gravar()


_FILA: Fila | None = None
_TRAVA_GLOBAL = threading.Lock()


def fila() -> Fila:
    global _FILA
    with _TRAVA_GLOBAL:
        if _FILA is None:
            _FILA = Fila()
        return _FILA


def reiniciar() -> None:
    """Para os testes: começa uma fila nova (lendo o registro da pasta atual)."""
    global _FILA
    with _TRAVA_GLOBAL:
        _FILA = None
