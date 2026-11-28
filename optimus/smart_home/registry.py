"""Registro local e seguro de dispositivos da casa inteligente.

O registro guarda metadados operacionais, nunca tokens, senhas ou URLs com credenciais.
A persistência usa gravação atômica para não corromper o inventário em interrupções.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_ESTADOS = {"confirmed", "estimated", "unavailable"}
_DISPONIBILIDADE = {"online", "offline", "unknown"}


@dataclass
class Dispositivo:
    id: str
    nome: str
    integracao: str
    fabricante: str = ""
    modelo: str = ""
    host: str = ""
    entity_id: str = ""
    comodo: str = ""
    capacidades: list[str] = field(default_factory=list)
    disponibilidade: str = "unknown"
    confianca_estado: str = "unavailable"
    ultimo_visto: str = ""

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.id):
            raise ValueError("id do dispositivo inválido")
        if not self.nome.strip() or not self.integracao.strip():
            raise ValueError("nome e integração são obrigatórios")
        if self.disponibilidade not in _DISPONIBILIDADE:
            raise ValueError("disponibilidade inválida")
        if self.confianca_estado not in _ESTADOS:
            raise ValueError("confianca_estado inválida")
        self.capacidades = sorted({str(c).strip() for c in self.capacidades if str(c).strip()})

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> "Dispositivo":
        campos = cls.__dataclass_fields__
        seguros = {k: v for k, v in dados.items() if k in campos}
        return cls(**seguros)


class RegistroDispositivos:
    """Inventário persistente em JSON, independente das credenciais de integrações."""

    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self._lock = threading.RLock()
        self._itens: dict[str, Dispositivo] = {}
        self._carregar()

    def _carregar(self) -> None:
        if not self.caminho.exists():
            return
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            if not isinstance(dados, dict) or dados.get("schema_version") != 1:
                return
            itens = dados.get("devices", [])
            if not isinstance(itens, list):
                return
            for item in itens:
                try:
                    dispositivo = Dispositivo.de_dict(item)
                    self._itens[dispositivo.id] = dispositivo
                except (TypeError, ValueError):
                    continue
        except (OSError, json.JSONDecodeError):
            # Um arquivo inválido não deve impedir a inicialização do Optimus.
            return

    def listar(self, integracao: str = "") -> list[dict[str, Any]]:
        with self._lock:
            itens = self._itens.values()
            if integracao:
                itens = (d for d in itens if d.integracao == integracao)
            return [asdict(d) for d in sorted(itens, key=lambda x: (x.comodo, x.nome, x.id))]

    def obter(self, dispositivo_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._itens.get(dispositivo_id)
            return asdict(item) if item else None

    def salvar(self, dispositivo: Dispositivo) -> None:
        if not isinstance(dispositivo, Dispositivo):
            raise TypeError("esperado Dispositivo")
        with self._lock:
            self._itens[dispositivo.id] = dispositivo
            self._persistir()

    def remover(self, dispositivo_id: str) -> bool:
        with self._lock:
            if dispositivo_id not in self._itens:
                return False
            del self._itens[dispositivo_id]
            self._persistir()
            return True

    def _persistir(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = {
            "schema_version": 1,
            "devices": [asdict(d) for d in sorted(
                self._itens.values(), key=lambda x: x.id
            )],
        }
        fd, temporario = tempfile.mkstemp(
            prefix=f".{self.caminho.name}.", suffix=".tmp", dir=self.caminho.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, ensure_ascii=False, indent=2)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporario, self.caminho)
        except Exception:
            try:
                os.unlink(temporario)
            except OSError:
                pass
            raise
