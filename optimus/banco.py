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
CREATE TABLE IF NOT EXISTS habitos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    criado REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS habito_marcacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habito INTEGER NOT NULL REFERENCES habitos(id) ON DELETE CASCADE,
    dia TEXT NOT NULL,
    quando REAL NOT NULL,
    UNIQUE (habito, dia)
);
CREATE TABLE IF NOT EXISTS timers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL DEFAULT 'Timer',
    criado REAL NOT NULL,
    termina REAL NOT NULL,
    duracao_seg INTEGER NOT NULL,
    tocado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS copiados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    texto TEXT NOT NULL,
    quando REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rotinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    criado REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rotina_passos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rotina INTEGER NOT NULL REFERENCES rotinas(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,
    texto TEXT NOT NULL
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

# Chaves das personas que já vêm no sistema: podem ser editadas, nunca excluídas.
PERSONAS_PADRAO = frozenset(p[0] for p in PERSONAS_INICIAIS)

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
        self.limpar_lixo_da_v01()

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
        """Só os fatos que têm a ver com a consulta (antes vinham todos, sempre)."""
        palavras = {p for p in re.findall(r"\w+", consulta.lower()) if len(p) > 3}
        if not palavras:
            return []
        pontuados = []
        for fato in self.fatos():
            nota = sum(p in fato["texto"].lower() for p in palavras)
            if nota:
                pontuados.append((nota, fato["texto"]))
        pontuados.sort(key=lambda item: -item[0])
        return [texto for _, texto in pontuados[:limite]]

    def buscar_mensagens(self, consulta: str, limite: int = 10) -> list[dict[str, Any]]:
        """Procura nas conversas antigas (memória de conversas anteriores)."""
        termos = [t for t in re.findall(r"\w+", consulta.lower()) if len(t) > 3][:6]
        if not termos:
            return []
        filtro = " OR ".join("lower(m.conteudo) LIKE ?" for _ in termos)
        return self._todos(
            "SELECT m.conversa, m.papel, substr(m.conteudo, 1, 400) AS trecho, m.quando, "
            f"c.titulo FROM mensagens m JOIN conversas c ON c.id = m.conversa WHERE {filtro} "
            "ORDER BY m.id DESC LIMIT ?", (*[f"%{t}%" for t in termos], limite))

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
        repetido = self._todos("SELECT id FROM lembretes WHERE feito=0 AND texto=? AND "
                               "abs(quando-?) < 600", (texto, quando))
        if repetido:  # o mesmo lembrete já existe: não duplica
            return repetido[0]["id"]
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

    def cancelar_lembretes(self, filtro: str = "") -> int:
        """Cancela os lembretes pendentes (todos, ou os que contêm o filtro)."""
        if filtro:
            return self._exec("DELETE FROM lembretes WHERE feito=0 AND lower(texto) LIKE ?",
                              (f"%{filtro.lower()}%",)).rowcount
        return self._exec("DELETE FROM lembretes WHERE feito=0").rowcount

    def limpar_lixo_da_v01(self) -> int:
        """A v0.1 com modelos pequenos chegou a criar lembretes e fatos com o próprio texto
        de sistema ("Fale em português do Brasil, educado..."). Remove esse lixo."""
        marcas = ("%fale em portugu%educado%", "%assistente pessoal%criado%",
                  "%assistente criado%", "%optimus voz%", "%direto e com%humor%")
        total = 0
        for marca in marcas:
            total += self._exec("DELETE FROM lembretes WHERE lower(texto) LIKE ?",
                                (marca,)).rowcount
            total += self._exec("DELETE FROM fatos WHERE lower(texto) LIKE ?", (marca,)).rowcount
        return total

    def apagar_lembrete(self, lembrete_id: int) -> None:
        self._exec("DELETE FROM lembretes WHERE id=?", (lembrete_id,))

    # Hábitos (acompanhamento diário com sequência/streak)
    @staticmethod
    def _hoje() -> str:
        return time.strftime("%Y-%m-%d", time.localtime())

    def criar_habito(self, nome: str) -> int:
        nome = nome.strip()
        # casefold (não o lower() do SQLite, que só dobra ASCII) para "Água" == "água".
        alvo = nome.casefold()
        existe = next((h for h in self._todos("SELECT id, nome FROM habitos")
                       if h["nome"].casefold() == alvo), None)
        if existe:
            return existe["id"]
        return self._exec("INSERT INTO habitos (nome, criado) VALUES (?,?)",
                          (nome, time.time())).lastrowid

    def marcar_habito(self, habito_id: int, dia: str | None = None) -> bool:
        """Marca o hábito como feito num dia (padrão: hoje). Idempotente por dia."""
        dia = dia or self._hoje()
        with self._trava:
            cur = self._con.execute(
                "INSERT OR IGNORE INTO habito_marcacoes (habito, dia, quando) VALUES (?,?,?)",
                (habito_id, dia, time.time()))
            self._con.commit()
            return cur.rowcount > 0

    def desmarcar_habito(self, habito_id: int, dia: str | None = None) -> None:
        self._exec("DELETE FROM habito_marcacoes WHERE habito=? AND dia=?",
                   (habito_id, dia or self._hoje()))

    def _sequencia(self, habito_id: int) -> int:
        """Dias seguidos até hoje (ou até ontem, se hoje ainda não foi marcado)."""
        dias = {d["dia"] for d in self._todos(
            "SELECT dia FROM habito_marcacoes WHERE habito=?", (habito_id,))}
        if not dias:
            return 0
        import datetime as _dt
        hoje = _dt.date.fromisoformat(self._hoje())
        inicio = hoje if hoje.isoformat() in dias else hoje - _dt.timedelta(days=1)
        seq = 0
        atual = inicio
        while atual.isoformat() in dias:
            seq += 1
            atual -= _dt.timedelta(days=1)
        return seq

    def listar_habitos(self) -> list[dict[str, Any]]:
        hoje = self._hoje()
        saida = []
        for h in self._todos("SELECT * FROM habitos ORDER BY criado"):
            total = self._todos("SELECT COUNT(*) AS n FROM habito_marcacoes WHERE habito=?",
                                (h["id"],))[0]["n"]
            feito_hoje = bool(self._todos(
                "SELECT 1 FROM habito_marcacoes WHERE habito=? AND dia=?", (h["id"], hoje)))
            saida.append({"id": h["id"], "nome": h["nome"], "sequencia": self._sequencia(h["id"]),
                          "feito_hoje": feito_hoje, "total": total})
        return saida

    def apagar_habito(self, habito_id: int) -> None:
        self._exec("DELETE FROM habitos WHERE id=?", (habito_id,))

    # Timers (contagem regressiva com nome)
    def criar_timer(self, nome: str, segundos: int) -> int:
        agora = time.time()
        return self._exec(
            "INSERT INTO timers (nome, criado, termina, duracao_seg) VALUES (?,?,?,?)",
            (nome.strip() or "Timer", agora, agora + segundos, int(segundos))).lastrowid

    def listar_timers(self, apenas_ativos: bool = True) -> list[dict[str, Any]]:
        agora = time.time()
        sql = "SELECT * FROM timers"
        if apenas_ativos:
            sql += " WHERE tocado=0"
        saida = []
        for t in self._todos(sql + " ORDER BY termina"):
            restante = t["termina"] - agora
            saida.append({**t, "restante_seg": max(0, round(restante)),
                          "vencido": restante <= 0})
        return saida

    def timers_vencidos(self) -> list[dict[str, Any]]:
        """Timers ativos que já chegaram ao fim (para a interface/voz tocar o alarme)."""
        return self._todos("SELECT * FROM timers WHERE tocado=0 AND termina<=? ORDER BY termina",
                           (time.time(),))

    def marcar_timer_tocado(self, timer_id: int) -> None:
        self._exec("UPDATE timers SET tocado=1 WHERE id=?", (timer_id,))

    def cancelar_timer(self, timer_id: int) -> None:
        self._exec("DELETE FROM timers WHERE id=?", (timer_id,))

    # Copiados (histórico da área de transferência)
    def guardar_copiado(self, texto: str, limite: int = 100) -> int | None:
        """Guarda um texto copiado, preservando espaços e quebras de linha. Ignora vazio e
        repetição do mais recente; uma cópia igual mais antiga sobe para o topo; mantém só
        os 'limite' últimos."""
        if not texto or not texto.strip():
            return None
        ultimo = self._todos("SELECT texto FROM copiados ORDER BY id DESC LIMIT 1")
        if ultimo and ultimo[0]["texto"] == texto:
            return None
        self._exec("DELETE FROM copiados WHERE texto=?", (texto,))
        novo = self._exec("INSERT INTO copiados (texto, quando) VALUES (?,?)",
                          (texto, time.time())).lastrowid
        self._exec("DELETE FROM copiados WHERE id NOT IN "
                   "(SELECT id FROM copiados ORDER BY id DESC LIMIT ?)", (max(1, int(limite)),))
        return novo

    def listar_copiados(self, limite: int = 50) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM copiados ORDER BY id DESC LIMIT ?", (max(1, int(limite)),))

    def copiado(self, copiado_id: int) -> dict[str, Any] | None:
        linhas = self._todos("SELECT * FROM copiados WHERE id=?", (int(copiado_id),))
        return linhas[0] if linhas else None

    def apagar_copiado(self, copiado_id: int) -> None:
        self._exec("DELETE FROM copiados WHERE id=?", (int(copiado_id),))

    def limpar_copiados(self) -> None:
        self._exec("DELETE FROM copiados")

    # Rotinas (sequências de passos disparadas por um nome)
    def criar_rotina(self, nome: str, passos: list[str]) -> int:
        """Cria (ou regrava, se já existir pelo mesmo nome) uma rotina com passos em ordem."""
        nome = (nome or "").strip() or "Rotina"
        # casefold (não o lower() do SQLite, que só dobra ASCII) para "CAFÉ" == "café".
        alvo = nome.casefold()
        existente = next((r for r in self._todos("SELECT id, nome FROM rotinas")
                          if r["nome"].casefold() == alvo), None)
        if existente:
            rid = existente["id"]
            self._exec("DELETE FROM rotina_passos WHERE rotina=?", (rid,))
        else:
            rid = self._exec("INSERT INTO rotinas (nome, criado) VALUES (?,?)",
                             (nome, time.time())).lastrowid
        ordem = 0
        for passo in passos or []:
            passo = (passo or "").strip()
            if passo:
                self._exec("INSERT INTO rotina_passos (rotina, ordem, texto) VALUES (?,?,?)",
                           (rid, ordem, passo))
                ordem += 1
        return rid

    def _com_passos(self, rotina: dict[str, Any]) -> dict[str, Any]:
        passos = self._todos("SELECT texto FROM rotina_passos WHERE rotina=? ORDER BY ordem",
                             (rotina["id"],))
        return {**rotina, "passos": [p["texto"] for p in passos]}

    def listar_rotinas(self) -> list[dict[str, Any]]:
        return [self._com_passos(r) for r in self._todos("SELECT * FROM rotinas ORDER BY nome")]

    def rotina_por_nome(self, nome: str) -> dict[str, Any] | None:
        alvo = (nome or "").strip().casefold()
        achada = next((r for r in self._todos("SELECT * FROM rotinas")
                       if r["nome"].casefold() == alvo), None)
        return self._com_passos(achada) if achada else None

    def apagar_rotina(self, rotina_id: int) -> None:
        self._exec("DELETE FROM rotinas WHERE id=?", (int(rotina_id),))

    # Personas e prompts
    def personas(self) -> list[dict[str, Any]]:
        linhas = self._todos("SELECT * FROM personas ORDER BY rowid")
        for linha in linhas:
            linha["embutida"] = linha.get("chave") in PERSONAS_PADRAO
        return linhas

    def persona(self, chave: str) -> dict[str, Any] | None:
        linhas = self._todos("SELECT * FROM personas WHERE chave=?", (chave,))
        return linhas[0] if linhas else None

    def salvar_persona(self, chave: str, nome: str, prompt: str, descricao: str = "",
                       modelo: str = "", voz: str = "") -> None:
        self._exec("INSERT OR REPLACE INTO personas VALUES (?,?,?,?,?,?)",
                   (chave, nome, descricao, prompt, modelo, voz))

    def apagar_persona(self, chave: str) -> None:
        # As personas que já vêm no sistema não podem ser excluídas, só editadas.
        if chave not in PERSONAS_PADRAO:
            self._exec("DELETE FROM personas WHERE chave=?", (chave,))

    def prompts(self) -> list[dict[str, Any]]:
        return self._todos("SELECT * FROM prompts ORDER BY categoria, titulo")

    def salvar_prompt(self, titulo: str, texto: str, categoria: str = "Geral") -> int:
        return self._exec("INSERT INTO prompts (titulo, texto, categoria) VALUES (?,?,?)",
                          (titulo, texto, categoria)).lastrowid

    def apagar_prompt(self, prompt_id: int) -> None:
        self._exec("DELETE FROM prompts WHERE id=?", (prompt_id,))
