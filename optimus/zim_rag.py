"""Indexação incremental e RAG local para arquivos ZIM.

Usa python-libzim quando instalado. O índice é SQLite/FTS5, com chunks,
proveniência e embeddings opcionais gerados pelo endpoint local do Ollama.
Nenhum conteúdo é enviado para serviços remotos.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
import sqlite3
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

MAX_ARTIGO = 2 * 1024 * 1024
TAMANHO_CHUNK = 900
SOBREPOSICAO = 120


class _TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self.ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg", "math"}:
            self.ignorar += 1
        elif tag.lower() in {"p", "br", "div", "li", "h1", "h2", "h3", "h4",
                             "tr", "section", "article"}:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg", "math"} and self.ignorar:
            self.ignorar -= 1
        elif tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4",
                             "tr", "section", "article"}:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self.ignorar:
            texto = data.strip()
            if texto:
                self.partes.append(texto)


def _texto(conteudo: bytes) -> str:
    bruto = conteudo.decode("utf-8", errors="replace")
    parser = _TextoHTML()
    try:
        parser.feed(bruto)
        saida = html.unescape(" ".join(parser.partes))
    except Exception:
        saida = re.sub(r"<[^>]+>", " ", bruto)
    saida = re.sub(r"[\t\r\f\v ]+", " ", saida)
    saida = re.sub(r" *\n *", "\n", saida)
    return saida.strip()


def _chunks(texto: str) -> list[str]:
    palavras = texto.split()
    if not palavras:
        return []
    saida, inicio = [], 0
    while inicio < len(palavras):
        fim = inicio
        chars = 0
        while fim < len(palavras) and chars + len(palavras[fim]) + 1 <= TAMANHO_CHUNK:
            chars += len(palavras[fim]) + 1
            fim += 1
        if fim == inicio:
            fim += 1
        parte = " ".join(palavras[inicio:fim]).strip()
        if len(parte) >= 40:
            saida.append(parte)
        if fim >= len(palavras):
            break
        # Sobreposição por caracteres aproximada em palavras, sem dividir tokens.
        recuo, total = fim, 0
        while recuo > inicio and total < SOBREPOSICAO:
            recuo -= 1
            total += len(palavras[recuo]) + 1
        inicio = max(inicio + 1, recuo)
    return saida


def _pasta() -> Path:
    from optimus.config import pasta_base
    destino = pasta_base() / "indice_zim"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_pasta() / "conhecimento_zim.sqlite3"), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS arquivos (
      nome TEXT PRIMARY KEY, caminho TEXT NOT NULL, tamanho INTEGER NOT NULL,
      mtime_ns INTEGER NOT NULL, cursor INTEGER NOT NULL DEFAULT 0,
      total INTEGER NOT NULL DEFAULT 0, concluido INTEGER NOT NULL DEFAULT 0,
      atualizado REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS trechos (
      id INTEGER PRIMARY KEY, arquivo TEXT NOT NULL, caminho_artigo TEXT NOT NULL,
      titulo TEXT NOT NULL, url TEXT NOT NULL, posicao INTEGER NOT NULL,
      texto TEXT NOT NULL, hash TEXT NOT NULL, embedding TEXT,
      UNIQUE(arquivo, caminho_artigo, posicao)
    );
    CREATE INDEX IF NOT EXISTS idx_trechos_arquivo ON trechos(arquivo);
    CREATE VIRTUAL TABLE IF NOT EXISTS trechos_fts USING fts5(
      titulo, texto, content='trechos', content_rowid='id',
      tokenize='unicode61 remove_diacritics 2'
    );
    CREATE TRIGGER IF NOT EXISTS trechos_ai AFTER INSERT ON trechos BEGIN
      INSERT INTO trechos_fts(rowid,titulo,texto) VALUES(new.id,new.titulo,new.texto);
    END;
    CREATE TRIGGER IF NOT EXISTS trechos_ad AFTER DELETE ON trechos BEGIN
      INSERT INTO trechos_fts(trechos_fts,rowid,titulo,texto)
      VALUES('delete',old.id,old.titulo,old.texto);
    END;
    CREATE TRIGGER IF NOT EXISTS trechos_au AFTER UPDATE ON trechos BEGIN
      INSERT INTO trechos_fts(trechos_fts,rowid,titulo,texto)
      VALUES('delete',old.id,old.titulo,old.texto);
      INSERT INTO trechos_fts(rowid,titulo,texto) VALUES(new.id,new.titulo,new.texto);
    END;
    """)
    con.commit()
    return con


def _modelo_auto(url: str, configurado: str = "") -> str:
    """Detecta embeddings apenas no Ollama local; nunca consulta endpoints remotos."""
    if not url or urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        return ""
    if configurado:
        return configurado
    try:
        import httpx
        resposta = httpx.get(url.rstrip("/") + "/api/tags", timeout=2.5)
        if resposta.status_code != 200:
            return ""
        nomes = [str(m.get("name") or "") for m in resposta.json().get("models", [])]
        preferidos = ("granite-embedding:278m", "embeddinggemma", "qwen3-embedding:0.6b",
                      "nomic-embed-text-v2-moe", "bge-m3", "paraphrase-multilingual",
                      "nomic-embed-text", "mxbai-embed-large", "snowflake-arctic-embed",
                      "all-minilm")
        for preferido in preferidos:
            encontrado = next((n for n in nomes if preferido in n.casefold()), "")
            if encontrado:
                return encontrado
    except Exception:
        pass
    return ""


def preparar_embedding(url: str, modelo: str = "") -> dict[str, Any]:
    """Garante um modelo de embeddings multilíngue após ação explícita de indexação."""
    if not url or urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        return {"instalado": False, "erro": "Ollama local indisponível; a indexação continuará em modo lexical."}
    existente = _modelo_auto(url, modelo)
    if existente:
        return {"instalado": True, "modelo": existente, "origem": "existente"}
    try:
        import httpx
        with httpx.stream(
            "POST", url.rstrip("/") + "/api/pull",
            json={"model": modelo or "granite-embedding:278m", "stream": True},
            timeout=httpx.Timeout(600, connect=5),
        ) as resposta:
            if resposta.status_code != 200:
                return {"instalado": False,
                        "erro": f"Ollama não conseguiu baixar o modelo de embeddings (HTTP {resposta.status_code})."}
            concluido = False
            for linha in resposta.iter_lines():
                if not linha:
                    continue
                dados = json.loads(linha)
                if dados.get("error"):
                    return {"instalado": False, "erro": str(dados["error"])[:500]}
                if dados.get("status") == "success":
                    concluido = True
            if not concluido:
                return {"instalado": False, "erro": "Ollama encerrou o download sem confirmar sucesso."}
        return {"instalado": True, "modelo": modelo or "granite-embedding:278m", "origem": "baixado"}
    except Exception as erro:
        return {"instalado": False, "erro": f"Falha ao preparar modelo de embeddings: {erro}"}


def _embeddings(url: str, modelo: str, textos: list[str]) -> list[list[float] | None]:
    """Gera embeddings em lotes pequenos para reduzir round-trips e pico de RAM."""
    if not url or not modelo or not textos:
        return [None] * len(textos)
    import httpx
    saida: list[list[float] | None] = []
    for inicio in range(0, len(textos), 16):
        lote = textos[inicio:inicio + 16]
        try:
            resposta = httpx.post(
                url.rstrip("/") + "/api/embed",
                json={"model": modelo, "input": [texto[:4000] for texto in lote], "keep_alive": 0},
                timeout=90,
            )
            if resposta.status_code != 200:
                saida.extend([None] * len(lote))
                continue
            vetores = resposta.json().get("embeddings") or []
            for vetor in vetores[:len(lote)]:
                saida.append([float(x) for x in vetor]
                             if isinstance(vetor, list) and vetor else None)
            saida.extend([None] * (len(lote) - len(vetores)))
        except Exception:
            saida.extend([None] * len(lote))
    return saida


def _embedding(url: str, modelo: str, texto: str) -> list[float] | None:
    return _embeddings(url, modelo, [texto])[0]


def _carregar_libzim():
    destino = _pasta().parent / "tools" / "python-packages"
    if destino.is_dir() and str(destino) not in sys.path:
        sys.path.insert(0, str(destino))
    from libzim.reader import Archive
    return Archive


def preparar_dependencia() -> dict[str, Any]:
    """Instala libzim em diretório privado do Optimus, sem PATH nem privilégios."""
    try:
        _carregar_libzim()
        return {"instalado": True, "origem": "ambiente"}
    except ImportError:
        pass
    destino = _pasta().parent / "tools" / "python-packages"
    destino.mkdir(parents=True, exist_ok=True)
    requisito = "libzim>=3.8.0" if sys.version_info >= (3, 11) else "libzim>=3.13.1,<4"
    comando = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               "--only-binary=:all:", "--upgrade", "--target", str(destino), requisito]
    try:
        processo = subprocess.run(comando, capture_output=True, text=True,
                                  timeout=300, check=False, shell=False)
    except (OSError, subprocess.TimeoutExpired) as erro:
        return {"instalado": False, "erro": f"Não foi possível preparar libzim: {erro}"}
    if processo.returncode != 0:
        detalhe = (processo.stderr or processo.stdout or "pip terminou com erro")[-1200:]
        return {"instalado": False, "erro": detalhe}
    import importlib
    importlib.invalidate_caches()
    try:
        _carregar_libzim()
    except ImportError as erro:
        return {"instalado": False, "erro": f"Pacote instalado, mas não carregou: {erro}"}
    return {"instalado": True, "origem": "diretorio_privado", "pasta": str(destino)}


def _archive_class():
    try:
        return _carregar_libzim()
    except ImportError:
        resultado = preparar_dependencia()
        if not resultado.get("instalado"):
            raise RuntimeError(resultado.get("erro") or "Não foi possível preparar libzim.")
        return _carregar_libzim()


def _iterar_entradas(arquivo):
    """Compatibiliza libzim 3.x (Python 3.10) e 4.x (Python >=3.11)."""
    iterador = getattr(arquivo, "iter_efficient", None)
    if callable(iterador):
        return iter(iterador())
    if hasattr(arquivo, "__iter__"):
        return iter(arquivo)
    quantidade = getattr(arquivo, "entry_count", None)
    if quantidade is None:
        quantidade = arquivo.all_entry_count
    getter = getattr(arquivo, "get_entry_by_id", None)
    if getter is None:
        getter = getattr(arquivo, "_get_entry_by_id", None)
    if getter is None:
        raise RuntimeError("Esta versão de libzim não oferece um iterador de artigos compatível.")
    return (getter(i) for i in range(int(quantidade)))


def indexar(arquivos: list[dict] | None = None, limite: int = 150,
            modelo_embedding: str = "", url_motor: str = "") -> dict[str, Any]:
    """Indexa até 'limite' artigos por execução e retoma pelo cursor salvo."""
    try:
        Archive = _archive_class()
    except RuntimeError as erro:
        return {"erro": str(erro), "dependencia": "libzim", "indexados": 0}
    from optimus import zim
    lista = arquivos if arquivos is not None else zim.listar_zim().get("arquivos", [])
    limite = max(1, min(int(limite), 1000))
    modelo_embedding = _modelo_auto(url_motor, modelo_embedding)
    preparo_embedding = None
    if not modelo_embedding and url_motor:
        preparo_embedding = preparar_embedding(url_motor)
        if preparo_embedding.get("instalado"):
            modelo_embedding = str(preparo_embedding.get("modelo") or "")
    total_novos = total_trechos = processados = vetores_atualizados = 0
    erros: list[dict] = []
    if preparo_embedding and not preparo_embedding.get("instalado"):
        erros.append({"arquivo": "embeddings", "erro": preparo_embedding.get("erro", "")})
    con = _db()
    try:
        # Remove do índice os arquivos que o catálogo completo já não encontra.
        if arquivos is None:
            presentes = {str(item.get("nome") or "") for item in lista}
            for registro in con.execute("SELECT nome FROM arquivos").fetchall():
                if registro["nome"] not in presentes:
                    con.execute("DELETE FROM trechos WHERE arquivo=?", (registro["nome"],))
                    con.execute("DELETE FROM arquivos WHERE nome=?", (registro["nome"],))
            con.commit()
        for item in lista:
            nome = str(item.get("nome") or "")
            caminho = (zim.pasta_biblioteca() / nome).resolve()
            if caminho.parent != zim.pasta_biblioteca().resolve() or not caminho.is_file() or caminho.is_symlink():
                continue
            stat = caminho.stat()
            assinatura = (stat.st_size, stat.st_mtime_ns)
            estado = con.execute("SELECT * FROM arquivos WHERE nome=?", (nome,)).fetchone()
            if estado and (estado["tamanho"], estado["mtime_ns"]) != assinatura:
                con.execute("DELETE FROM trechos WHERE arquivo=?", (nome,))
                con.execute("DELETE FROM arquivos WHERE nome=?", (nome,))
                estado = None
            # Se o usuário instalar um modelo de embeddings depois da indexação lexical,
            # preenche vetores faltantes sem reextrair os artigos do ZIM.
            if modelo_embedding:
                faltantes = con.execute(
                    "SELECT id,texto FROM trechos WHERE arquivo=? AND embedding IS NULL LIMIT ?",
                    (nome, limite)).fetchall()
                vetores = _embeddings(
                    url_motor, modelo_embedding, [r["texto"] for r in faltantes])
                for trecho_existente, vetor in zip(faltantes, vetores):
                    if vetor:
                        con.execute("UPDATE trechos SET embedding=? WHERE id=?",
                                    (json.dumps(vetor), trecho_existente["id"]))
                        vetores_atualizados += 1
                con.commit()
            if estado and estado["concluido"]:
                continue
            cursor = int(estado["cursor"]) if estado else 0
            try:
                with Archive(str(caminho)) as arquivo:
                    total_entradas = getattr(arquivo, "entry_count", None)
                    if total_entradas is None:
                        total_entradas = getattr(arquivo, "all_entry_count", None)
                    if total_entradas is None:
                        total_entradas = getattr(arquivo, "entryCount", None)
                    if total_entradas is None:
                        raise RuntimeError("A versão de libzim não informa a quantidade de entradas.")
                    total = int(total_entradas)
                    if estado is None:
                        con.execute("INSERT INTO arquivos(nome,caminho,tamanho,mtime_ns,cursor,total,concluido,atualizado) VALUES(?,?,?,?,0,?,0,?)",
                                    (nome, str(caminho), *assinatura, total, time.time()))
                        con.commit()
                    proximo = cursor
                    for indice, entrada in enumerate(_iterar_entradas(arquivo)):
                        if indice < cursor:
                            continue
                        if processados >= limite:
                            break
                        processados += 1
                        proximo = indice + 1
                        try:
                            if getattr(entrada, "is_redirect", False):
                                con.execute("UPDATE arquivos SET cursor=?,atualizado=? WHERE nome=?",
                                            (proximo, time.time(), nome))
                                continue
                            item_zim = entrada.get_item()
                            mime = str(getattr(item_zim, "mimetype", "") or "").lower()
                            if mime and not ("html" in mime or "text/plain" in mime or "xhtml" in mime):
                                con.execute("UPDATE arquivos SET cursor=?,atualizado=? WHERE nome=?",
                                            (proximo, time.time(), nome))
                                continue
                            tamanho = int(getattr(item_zim, "size", 0) or 0)
                            if tamanho <= 0 or tamanho > MAX_ARTIGO:
                                con.execute("UPDATE arquivos SET cursor=?,atualizado=? WHERE nome=?",
                                            (proximo, time.time(), nome))
                                continue
                            conteudo = bytes(item_zim.content)
                            texto = _texto(conteudo)
                            partes = _chunks(texto)
                            vetores = (_embeddings(url_motor, modelo_embedding, partes)
                                       if modelo_embedding else [])
                            titulo = str(getattr(entrada, "title", "") or entrada.path)[:500]
                            artigo = str(entrada.path)[:1000]
                            for posicao, trecho in enumerate(partes):
                                digest = hashlib.sha256(trecho.encode("utf-8")).hexdigest()
                                anterior = con.execute(
                                    "SELECT id,hash FROM trechos WHERE arquivo=? AND caminho_artigo=? AND posicao=?",
                                    (nome, artigo, posicao)).fetchone()
                                if anterior and anterior["hash"] == digest:
                                    continue
                                vetor = vetores[posicao] if posicao < len(vetores) else None
                                url = f"zim://{nome}/{artigo}"
                                if anterior:
                                    con.execute("UPDATE trechos SET titulo=?,url=?,texto=?,hash=?,embedding=? WHERE id=?",
                                                (titulo, url, trecho, digest,
                                                 json.dumps(vetor) if vetor else None, anterior["id"]))
                                else:
                                    con.execute("INSERT INTO trechos(arquivo,caminho_artigo,titulo,url,posicao,texto,hash,embedding) VALUES(?,?,?,?,?,?,?,?)",
                                                (nome, artigo, titulo, url, posicao, trecho, digest,
                                                 json.dumps(vetor) if vetor else None))
                                total_trechos += 1
                            total_novos += 1
                        except Exception as erro:
                            erros.append({"arquivo": nome, "artigo": str(getattr(entrada, "path", "")),
                                          "erro": f"{type(erro).__name__}: {erro}"[:300]})
                        con.execute("UPDATE arquivos SET cursor=?,atualizado=? WHERE nome=?",
                                    (proximo, time.time(), nome))
                        con.commit()
                    # Se o último item foi processado no limite do lote, concluir já.
                    # Caso contrário, manter o cursor para a próxima execução.
                    if proximo >= total:
                        con.execute("UPDATE arquivos SET concluido=1,cursor=?,atualizado=? WHERE nome=?",
                                    (total, time.time(), nome))
                    con.commit()
            except Exception as erro:
                erros.append({"arquivo": nome, "erro": f"{type(erro).__name__}: {erro}"[:300]})
    finally:
        con.close()
    return {"indexados": total_novos, "trechos": total_trechos,
            "embeddings_atualizados": vetores_atualizados,
            "artigos_processados": processados, "limite": limite,
            "modelo_embedding": modelo_embedding or None,
            "preparo_embedding": preparo_embedding, "erros": erros, "estado": status()}


def _vetor_norma(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v)) or 1.0


def _similaridade(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (_vetor_norma(a) * _vetor_norma(b))


def buscar(consulta: str, limite: int = 6, modelo_embedding: str = "",
           url_motor: str = "") -> list[dict[str, Any]]:
    """Recuperação híbrida: FTS5 + similaridade cosseno; fallback lexical."""
    consulta = str(consulta or "").strip()
    if len(consulta) < 2:
        return []
    con = _db()
    try:
        termos = [t for t in re.findall(r"[\wÀ-ÿ]+", consulta) if len(t) > 1][:12]
        if not termos:
            return []
        expressao = " OR ".join('"' + t.replace('"', '""') + '"' for t in termos)
        try:
            lexicais = con.execute(
                "SELECT t.*,bm25(trechos_fts) AS rank FROM trechos_fts "
                "JOIN trechos t ON t.id=trechos_fts.rowid WHERE trechos_fts MATCH ? "
                "ORDER BY rank LIMIT 80", (expressao,)).fetchall()
        except sqlite3.OperationalError:
            lexicais = []
        candidatos = {int(r["id"]): dict(r) for r in lexicais}
        # Não consulta o servidor Ollama em cada conversa quando o índice ainda é lexical.
        tem_vetores = con.execute(
            "SELECT 1 FROM trechos WHERE embedding IS NOT NULL LIMIT 1").fetchone()
        if tem_vetores and not modelo_embedding:
            modelo_embedding = _modelo_auto(url_motor)
        consulta_vetor = (_embedding(url_motor, modelo_embedding, consulta)
                          if tem_vetores and modelo_embedding else None)
        vetoriais = []
        if consulta_vetor:
            # A varredura fica limitada a 5.000 vetores para proteger PCs modestos.
            for r in con.execute("SELECT * FROM trechos WHERE embedding IS NOT NULL LIMIT 5000"):
                try:
                    score = _similaridade(consulta_vetor, json.loads(r["embedding"]))
                    vetoriais.append((score, dict(r)))
                except (ValueError, TypeError):
                    continue
            vetoriais.sort(key=lambda x: x[0], reverse=True)
            for score, r in vetoriais[:80]:
                r["score_vetor"] = score
                candidatos[int(r["id"])] = r
        resultados = []
        for r in candidatos.values():
            texto = (r["titulo"] + " " + r["texto"]).casefold()
            cobertura = sum(1 for t in termos if t.casefold() in texto)
            lexical = cobertura / max(1, len(termos))
            vetor = float(r.get("score_vetor", 0))
            # RRF-like fusion: normaliza as duas fontes sem deixar o BM25 dominar.
            score = 0.65 * lexical + 0.35 * max(0.0, vetor)
            resultados.append({"titulo": r["titulo"], "trecho": r["texto"],
                               "arquivo": r["arquivo"], "artigo": r["caminho_artigo"],
                               "url": r["url"], "hash_trecho": r["hash"],
                               "citacao": f"{r['titulo']} — {r['arquivo']}#{r['caminho_artigo']}",
                               "score": round(score, 4), "tipo_fonte": "ZIM"})
        resultados.sort(key=lambda x: x["score"], reverse=True)
        return resultados[:max(1, min(int(limite), 20))]
    finally:
        con.close()


def status() -> dict[str, Any]:
    con = _db()
    try:
        arquivos = [dict(r) for r in con.execute(
            "SELECT nome,tamanho,total,cursor,concluido,atualizado FROM arquivos ORDER BY nome")]
        return {"arquivos": arquivos, "artigos_indexados": int(con.execute(
            "SELECT COUNT(DISTINCT arquivo || ':' || caminho_artigo) FROM trechos").fetchone()[0]),
            "trechos": int(con.execute("SELECT COUNT(*) FROM trechos").fetchone()[0]),
            "com_embeddings": int(con.execute(
                "SELECT COUNT(*) FROM trechos WHERE embedding IS NOT NULL").fetchone()[0])}
    finally:
        con.close()
