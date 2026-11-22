"""Audiolivros e narrações longas: TXT, Markdown, EPUB, PDF ou DOCX viram áudio por capítulo.

- Divide em capítulos sozinho ("Capítulo 1", "CAPÍTULO II", "Chapter", títulos `#`), ou em
  partes de tamanho parecido quando o texto não tem capítulos.
- Gera cada capítulo uma vez e guarda: se parar, recomeça de onde parou.
- Entrega um MP3 por capítulo e, se pedir, um único **M4B** com marcadores de capítulo e capa
  (o formato que os apps de audiolivro usam).
"""

from __future__ import annotations

import hashlib
import html
import re
import zipfile
from pathlib import Path

from optimus.estudio import audio, motores, pasta_estudio, pasta_saidas, registrar, vozes
from optimus.estudio.audio import ErroEstudio

TAXA = motores.TAXA
_TITULO = re.compile(
    r"^\s*(?:#{1,3}\s+.+|(?:cap[ií]tulo|chapter|parte|part|pr[oó]logo|ep[ií]logo|"
    r"introdu[cç][aã]o)\b.{0,80})\s*$", re.IGNORECASE | re.MULTILINE)


# ---------------------------------------------------------------------- ler o livro
def _sem_tags(conteudo: str) -> str:
    conteudo = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", conteudo)
    conteudo = re.sub(r"(?i)<\s*(h[1-6])[^>]*>(.*?)</\s*\1\s*>", r"\n\n# \2\n\n", conteudo)
    conteudo = re.sub(r"(?i)<\s*(br|/p|/div|/li)[^>]*>", "\n", conteudo)
    conteudo = re.sub(r"<[^>]+>", "", conteudo)
    return html.unescape(conteudo)


def _epub(caminho: Path) -> str:
    with zipfile.ZipFile(caminho) as z:
        nomes = z.namelist()
        container = z.read("META-INF/container.xml").decode("utf-8", "replace") \
            if "META-INF/container.xml" in nomes else ""
        opf_nome = (re.search(r'full-path="([^"]+)"', container) or [None, ""])[1]
        ordem: list[str] = []
        if opf_nome and opf_nome in nomes:
            opf = z.read(opf_nome).decode("utf-8", "replace")
            base = opf_nome.rsplit("/", 1)[0] + "/" if "/" in opf_nome else ""
            itens = dict(re.findall(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', opf))
            itens.update({i: h for h, i in re.findall(
                r'<item\b[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', opf)})
            for idref in re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf):
                if idref in itens:
                    ordem.append(base + itens[idref])
        if not ordem:
            ordem = sorted(n for n in nomes if n.lower().endswith((".xhtml", ".html", ".htm")))
        return "\n\n".join(_sem_tags(z.read(n).decode("utf-8", "replace"))
                           for n in ordem if n in nomes)


def _docx(caminho: Path) -> str:
    with zipfile.ZipFile(caminho) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def _pdf(caminho: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as erro:
        raise ErroEstudio("Para ler PDF, instale: pip install pypdf") from erro
    return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(caminho)).pages)


def ler_livro(caminho: str | Path) -> str:
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroEstudio(f"Arquivo não encontrado: {caminho}")
    ext = caminho.suffix.lower()
    if ext == ".epub":
        texto = _epub(caminho)
    elif ext == ".docx":
        texto = _docx(caminho)
    elif ext == ".pdf":
        texto = _pdf(caminho)
    elif ext in (".html", ".htm", ".xhtml"):
        texto = _sem_tags(caminho.read_text(encoding="utf-8", errors="replace"))
    else:
        texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"-\n(\w)", r"\1", texto)  # palavras hifenizadas na quebra de linha
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


# ---------------------------------------------------------------------- capítulos
def capitulos(texto: str, max_palavras: int = 4000) -> list[tuple[str, str]]:
    """[(título, texto)]. Sem títulos no texto, divide em partes de até `max_palavras`."""
    marcas = list(_TITULO.finditer(texto))
    saida: list[tuple[str, str]] = []
    if marcas:
        if texto[:marcas[0].start()].strip():
            saida.append(("Início", texto[:marcas[0].start()].strip()))
        for i, m in enumerate(marcas):
            fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
            corpo = texto[m.end():fim].strip()
            titulo = m.group(0).strip().lstrip("#").strip()
            if corpo:
                saida.append((titulo[:80], corpo))
            elif saida:  # título seguido de outro título: junta no próximo
                continue
    if not saida:
        paragrafos = [p for p in re.split(r"\n\s*\n", texto) if p.strip()]
        atual: list[str] = []
        contagem = 0
        for par in paragrafos:
            atual.append(par)
            contagem += len(par.split())
            if contagem >= max_palavras:
                saida.append((f"Parte {len(saida) + 1}", "\n\n".join(atual)))
                atual, contagem = [], 0
        if atual:
            saida.append((f"Parte {len(saida) + 1}", "\n\n".join(atual)))
    return saida


# ---------------------------------------------------------------------- gerar
def _metadados_capitulos(titulo: str, autor: str, partes: list[tuple[str, float]]) -> str:
    def esc(t: str) -> str:
        return re.sub(r"([=;#\\\n])", r"\\\1", t)

    linhas = [";FFMETADATA1", f"title={esc(titulo)}", f"artist={esc(autor)}",
              f"album={esc(titulo)}", "genre=Audiobook", f"comment={audio.MARCA_IA}"]
    inicio = 0.0
    for nome, segundos in partes:
        linhas += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(inicio * 1000)}",
                   f"END={int((inicio + segundos) * 1000)}", f"title={esc(nome)}"]
        inicio += segundos
    return "\n".join(linhas) + "\n"


def gerar(arquivo: str | Path, voz: str = "", idioma: str = "", titulo: str = "",
          autor: str = "", capa: str | Path | None = None, m4b: bool = True,
          velocidade: float = 1.0, so_capitulos: list[int] | None = None, config=None,
          progresso=None, cancelado=None, saida: str | Path | None = None) -> dict:
    arquivo = Path(arquivo)
    texto = ler_livro(arquivo)
    if not texto:
        raise ErroEstudio("O arquivo não tem texto para narrar.")
    caps = capitulos(texto)
    perfil = vozes.obter(voz)
    titulo = titulo or arquivo.stem.replace("_", " ")
    chave = hashlib.sha1(f"{arquivo.resolve()}|{perfil.id}|{idioma}|{velocidade}".encode()
                         ).hexdigest()[:10]
    trabalho = pasta_estudio() / "audiolivros" / f"{arquivo.stem[:30]}-{chave}"
    trabalho.mkdir(parents=True, exist_ok=True)
    destino = (Path(saida) if saida else pasta_saidas(config)) / titulo[:60]
    destino.mkdir(parents=True, exist_ok=True)
    total_palavras = sum(len(c.split()) for _, c in caps) or 1
    feitas, arquivos, duracoes = 0, [], []
    for n, (nome, corpo) in enumerate(caps, 1):
        if so_capitulos and n not in so_capitulos:
            continue
        if cancelado and cancelado():
            raise ErroEstudio("Cancelado.")
        cache = trabalho / f"{n:03d}-{hashlib.sha1(corpo.encode()).hexdigest()[:8]}.wav"
        if progresso:
            progresso(feitas / total_palavras, f"Capítulo {n} de {len(caps)}: {nome}")
        if cache.exists():
            x, _ = audio.ler_wav(cache.read_bytes())
        else:
            x = motores.gerar(f"{nome}.\n\n{corpo}", perfil, idioma, velocidade, config,
                              cancelado=cancelado)
            cache.write_bytes(audio.wav_bytes(x, TAXA))
        seguro = re.sub(r'[\\/:*?"<>|]+', "", nome)[:50].strip() or f"Capitulo {n}"
        arquivos.append(str(audio.salvar(x, TAXA, destino / f"{n:03d} - {seguro}.mp3",
                                         titulo=nome)))
        duracoes.append((nome, len(x) / TAXA))
        feitas += len(corpo.split())
    resultado = {"titulo": titulo, "voz": perfil.nome, "capitulos": len(arquivos),
                 "pasta": str(destino), "arquivos": arquivos,
                 "duracao_min": round(sum(d for _, d in duracoes) / 60, 1)}
    if m4b and arquivos and not so_capitulos:
        (progresso or (lambda *a: None))(0.97, "Montando o audiolivro (M4B)…")
        lista = trabalho / "lista.txt"
        def citar(caminho: str) -> str:  # aspas simples escapadas como o ffmpeg espera
            return "'" + Path(caminho).resolve().as_posix().replace("'", "'\\''") + "'"

        lista.write_text("".join(f"file {citar(a)}\n" for a in arquivos), encoding="utf-8")
        meta = trabalho / "capitulos.txt"
        meta.write_text(_metadados_capitulos(titulo, autor or perfil.nome, duracoes),
                        encoding="utf-8")
        nome_livro = re.sub(r"[^\w -]+", "", titulo)[:60].strip() or "audiolivro"
        livro = destino / f"{nome_livro}.m4b"
        args = ["-f", "concat", "-safe", "0", "-i", str(lista), "-i", str(meta)]
        if capa and Path(capa).exists():
            args += ["-i", str(capa), "-map", "0:a", "-map", "2:v", "-c:v", "mjpeg",
                     "-disposition:v:0", "attached_pic"]
        else:
            args += ["-map", "0:a"]
        args += ["-map_metadata", "1", "-map_chapters", "1", "-c:a", "aac", "-b:a", "96k",
                 str(livro)]
        audio._rodar(args)
        resultado["audiolivro"] = str(livro)
    registrar("audiolivro", resultado.get("audiolivro") or destino, titulo, perfil.nome, idioma)
    return resultado
