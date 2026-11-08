"""Banco local (SQLite): conversas, projetos, memória de longo prazo, lembretes,
personas e biblioteca de prompts. Tudo fica no PC do usuário."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL DEFAULT 'Nova conversa',
    projeto TEXT NOT NULL DEFAULT '',
    persona TEXT NOT NULL DEFAULT 'optimus',
    criada REAL NOT NULL,
    atualizada REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa INTEGER NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    papel TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    extra TEXT NOT NULL DEFAULT '{}',
    quando REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS fatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    texto TEXT NOT NULL UNIQUE,
    quando REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS lembretes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    texto TEXT NOT NULL,
    quando REAL NOT NULL,
    repetir_minutos INTEGER NOT NULL DEFAULT 0,
    feito INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS personas (
    chave TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    modelo TEXT NOT NULL DEFAULT '',
    voz TEXT NOT NULL DEFAULT ''
);
CREATE VIRTUAL TABLE IF NOT EXISTS conhecimento USING fts5(
    fonte, titulo, trecho, quando UNINDEXED, tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    texto TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'Geral'
);
"""

PERSONAS_INICIAIS = [
    ("optimus", "Optimus", "Assistente pessoal completo, com ferramentas", "", "", ""),
    ("pesquisador", "Pesquisador", "Pesquisa a fundo na internet e cita as fontes",
     "Você é um pesquisador meticuloso. Para cada pergunta, pesquise em várias fontes, leia as "
     "páginas mais relevantes e responda com um resumo organizado e a lista de links usados.",
     "", ""),
    ("programador", "Programador", "Escreve, explica e roda código",
     "Você é um programador sênior. Escreva código completo e funcional, explique as decisões "
     "em poucas linhas e, quando puder, rode o código para conferir antes de responder.", "", ""),
    ("livre", "Livre", "Sem personalidade definida: só o modelo que você escolheu",
     "Responda ao usuário.", "", ""),
]

PROMPTS_INICIAIS = [
    ("Resumo do dia", "Me dê um resumo do dia: data, hora, lembretes pendentes, estado do PC "
     "e as 5 notícias mais importantes do Brasil hoje.", "Rotina"),
    ("Organizar Downloads", "Liste a pasta Downloads, agrupe os arquivos por tipo e proponha "
     "como organizar em pastas. Só mova depois que eu aprovar.", "PC"),
    ("Saúde do PC", "Verifique CPU, memória, disco e os processos que mais consomem recursos e "
     "me diga se tem algo errado.", "PC"),
    ("Pesquisa profunda", "Pesquise a fundo sobre: ", "Internet"),
    ("Explicar código", "Explique este código linha por linha:\n", "Código"),
    ("Traduzir", "Traduza para o inglês mantendo o tom:\n", "Texto"),
]


class Banco:
    def __init__(self, caminho: Path):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho = caminho
        self._trava = threading.RLock()
        self._con = sqlite3.connect(str(caminho), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA foreign_keys = ON")
        self._con.executescript(_ESQUEMA)
        if not self._con.execute("SELECT 1 FROM personas LIMIT 1").fetchone():
            self._con.executemany("INSERT INTO personas VALUES (?,?,?,?,?,?)", PERSONAS_INICIAIS)
        if not self._con.execute("SELECT 1 FROM prompts LIMIT 1").fetchone():
            self._con.executemany("INSERT INTO prompts (titulo, texto, categoria) VALUES (?,?,?)",
                                  PROMPTS_INICIAIS)
        self._con.commit()

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._trava:
            cursor = self._con.execute(sql, args)
            self._con.commit()
            return cursor

    def _todos(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._trava:
            return [dict(l) for l in self._con.execute(sql, args).fetchall()]

    # Conversas
    def nova_conversa(self, titulo: str = "Nova conversa", projeto: str = "",
                      persona: str = "optimus") -> int:
        agora = time.time()
        return self._exec(
            "INSERT INTO conversas (titulo, projeto, persona, criada, atualizada) "
            "VALUES (?,?,?,?,?)", (titulo, projeto, persona, agora, agora)).lastrowid

    def conversas(self, projeto: str | None = None) -> list[dict[str, Any]]:
        if projeto is None:
            return self._todos("SELECT * FROM conversas ORDER BY atualizada DESC")
        return self._todos("SELECT * FROM conversas WHERE projeto=? ORDER BY atualizada DESC",
                           (projeto,))

    def conversa(self, conversa_id: int) -> dict[str, Any] | None:
        linhas = self._todos("SELECT * FROM conversas WHERE id=?", (conversa_id,))
        return linhas[0] if linhas else None

    def atualizar_conversa(self, conversa_id: int, **campos) -> None:
        permitidos = {k: v for k, v in campos.items() if k in ("titulo", "projeto", "persona")}
        if not permitidos:
            return
        partes = ", ".join(f"{k}=?" for k in permitidos)
        self._exec(f"UPDATE conversas SET {partes}, atualizada=? WHERE id=?",
                   (*permitidos.values(), time.time(), conversa_id))

    def apagar_conversa(self, conversa_id: int) -> None:
        self._exec("DELETE FROM conversas WHERE id=?", (conversa_id,))

    def projetos(self) -> list[str]:
        return [l["projeto"] for l in self._todos(
            "SELECT DISTINCT projeto FROM conversas WHERE projeto<>'' ORDER BY projeto")]

    def adicionar_mensagem(self, conversa_id: int, papel: str, conteudo: str,
                           extra: dict | None = None) -> None:
        agora = time.time()
        self._exec("INSERT INTO mensagens (conversa, papel, conteudo, extra, quando) "
                   "VALUES (?,?,?,?,?)",
                   (conversa_id, papel, conteudo, json.dumps(extra or {}, ensure_ascii=False),
                    agora))
        self._exec("UPDATE conversas SET atualizada=? WHERE id=?", (agora, conversa_id))

    def mensagens(self, conversa_id: int, limite: int = 200) -> list[dict[str, Any]]:
        linhas = self._todos(
            "SELECT * FROM (SELECT * FROM mensagens WHERE conversa=? ORDER BY id DESC LIMIT ?) "
            "ORDER BY id", (conversa_id, limite))
        for linha in linhas:
            linha["extra"] = json.loads(linha["extra"] or "{}")
        return linhas

    # Memória de longo prazo
    def lembrar_fato(self, texto: str) -> None:
        self._exec("INSERT OR IGNORE INTO fatos (texto, quando) VALUES (?,?)",
                   (texto.strip(), time.time()))

    def fatos(self) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM fatos ORDER BY id")

    def esquecer_fato(self, fato_id: int) -> None:
        self._exec("DELETE FROM fatos WHERE id=?", (fato_id,))

    def buscar_fatos(self, consulta: str, limite: int = 8) -> list[str]:
        palavras = [p for p in consulta.lower().split() if len(p) > 3]
        todos = [f["texto"] for f in self.fatos()]
        if not palavras:
            return todos[-limite:]
        pontuados = sorted(todos, key=lambda t: -sum(p in t.lower() for p in palavras))
        return pontuados[:limite]

    # Base de conhecimento (o que o Optimus aprendeu com sites, arquivos e textos)
    def aprender(self, fonte: str, titulo: str, texto: str, tamanho: int = 1200) -> int:
        self._exec("DELETE FROM conhecimento WHERE fonte=?", (fonte,))
        paragrafos = [p.strip() for p in texto.split("\n") if p.strip()]
        trechos, atual = [], ""
        for paragrafo in paragrafos:
            if len(atual) + len(paragrafo) > tamanho and atual:
                trechos.append(atual)
                atual = ""
            atual += paragrafo + "\n"
        if atual.strip():
            trechos.append(atual)
        agora = time.time()
        with self._trava:
            self._con.executemany(
                "INSERT INTO conhecimento (fonte, titulo, trecho, quando) VALUES (?,?,?,?)",
                [(fonte, titulo, t, agora) for t in trechos])
            self._con.commit()
        return len(trechos)

    def consultar(self, consulta: str, limite: int = 5) -> list[dict[str, Any]]:
        termos = [t for t in re.findall(r"\w+", consulta) if len(t) > 2]
        if not termos:
            return []
        expressao = " OR ".join(f'"{t}"' for t in termos)
        return self._todos("SELECT fonte, titulo, trecho FROM conhecimento WHERE conhecimento "
                           "MATCH ? ORDER BY bm25(conhecimento) LIMIT ?", (expressao, limite))

    def fontes(self) -> list[dict[str, Any]]:
        return self._todos("SELECT fonte, titulo, COUNT(*) AS trechos, MAX(quando) AS quando "
                           "FROM conhecimento GROUP BY fonte ORDER BY quando DESC")

    def esquecer_fonte(self, fonte: str) -> None:
        self._exec("DELETE FROM conhecimento WHERE fonte=?", (fonte,))

    # Lembretes
    def criar_lembrete(self, texto: str, quando: float, repetir_minutos: int = 0) -> int:
        return self._exec("INSERT INTO lembretes (texto, quando, repetir_minutos) VALUES (?,?,?)",
                          (texto, quando, repetir_minutos)).lastrowid

    def lembretes(self, pendentes: bool = True) -> list[dict[str, Any]]:
        if pendentes:
            return self._todos("SELECT * FROM lembretes WHERE feito=0 ORDER BY quando")
        return self._todos("SELECT * FROM lembretes ORDER BY quando DESC")

    def lembretes_vencidos(self) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM lembretes WHERE feito=0 AND quando<=? ORDER BY quando",
                           (time.time(),))

    def concluir_lembrete(self, lembrete: dict[str, Any]) -> None:
        if lembrete.get("repetir_minutos"):
            self._exec("UPDATE lembretes SET quando=? WHERE id=?",
                       (time.time() + lembrete["repetir_minutos"] * 60, lembrete["id"]))
        else:
            self._exec("UPDATE lembretes SET feito=1 WHERE id=?", (lembrete["id"],))

    def apagar_lembrete(self, lembrete_id: int) -> None:
        self._exec("DELETE FROM lembretes WHERE id=?", (lembrete_id,))

    # Personas e prompts
    def personas(self) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM personas ORDER BY rowid")

    def persona(self, chave: str) -> dict[str, Any] | None:
        linhas = self._todos("SELECT * FROM personas WHERE chave=?", (chave,))
        return linhas[0] if linhas else None

    def salvar_persona(self, chave: str, nome: str, prompt: str, descricao: str = "",
                       modelo: str = "", voz: str = "") -> None:
        self._exec("INSERT OR REPLACE INTO personas VALUES (?,?,?,?,?,?)",
                   (chave, nome, descricao, prompt, modelo, voz))

    def apagar_persona(self, chave: str) -> None:
        if chave != "optimus":
            self._exec("DELETE FROM personas WHERE chave=?", (chave,))

    def prompts(self) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM prompts ORDER BY categoria, titulo")

    def salvar_prompt(self, titulo: str, texto: str, categoria: str = "Geral") -> int:
        return self._exec("INSERT INTO prompts (titulo, texto, categoria) VALUES (?,?,?)",
                          (titulo, texto, categoria)).lastrowid

    def apagar_prompt(self, prompt_id: int) -> None:
        self._exec("DELETE FROM prompts WHERE id=?", (prompt_id,))
