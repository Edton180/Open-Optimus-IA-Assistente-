"""Ferramentas de PDF: juntar, dividir, extrair, girar, proteger, OCR, converter etc.

Usa pypdf (obrigatório no extra [documentos]). OCR e renderização de páginas pedem
pypdfium2 + pytesseract + Tesseract instalado no sistema. Conversões Word/PPT/Excel
dependem do LibreOffice (soffice) quando disponíveis.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from html import escape as html_escape
from io import BytesIO
from pathlib import Path

from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, numero, texto


def _precisa_pypdf():
    try:
        from pypdf import PdfReader, PdfWriter  # noqa: F401
        return None
    except ImportError:
        return {"erro": "Instale o suporte a PDF: pip install \"optimus-assistente[documentos]\""}


def _caminho(ctx, caminho: str) -> Path:
    p = Path(caminho).expanduser()
    if not p.is_absolute() and ctx and getattr(ctx, "pasta_trabalho", None):
        p = Path(ctx.pasta_trabalho) / p
    return p.resolve()


def _paginas_parse(s: str, total: int) -> list[int]:
    if not s or not s.strip():
        return list(range(total))
    indices = set()
    for parte in re.split(r"[,\s]+", s.strip()):
        if not parte:
            continue
        if "-" in parte:
            a, b = parte.split("-", 1)
            try:
                inicio, fim = int(a), int(b)
            except ValueError:
                continue
            for i in range(min(inicio, fim), max(inicio, fim) + 1):
                if 1 <= i <= total:
                    indices.add(i - 1)
        else:
            try:
                i = int(parte)
                if 1 <= i <= total:
                    indices.add(i - 1)
            except ValueError:
                continue
    return sorted(indices)


def _ordem_paginas_parse(s: str, total: int) -> list[int]:
    """Interpreta a ordem informada sem ordenar nem remover repetições."""
    if not s or not s.strip():
        return list(range(total))
    indices = []
    for parte in re.split(r"[,\\s]+", s.strip()):
        if not parte:
            continue
        try:
            if "-" in parte:
                a, b = (int(v) for v in parte.split("-", 1))
                passo = 1 if b >= a else -1
                candidatos = range(a, b + passo, passo)
            else:
                candidatos = (int(parte),)
        except ValueError:
            continue
        indices.extend(i - 1 for i in candidatos if 1 <= i <= total)
    return indices


def _sobrepor_texto(pagina, texto: str, marca: bool = False) -> None:
    """Aplica texto visível à página. Requer reportlab; não cria assinatura digital."""
    try:
        from reportlab.lib.colors import Color
        from reportlab.pdfgen import canvas
        from pypdf import PdfReader
    except ImportError as erro:
        raise RuntimeError(
            'Este recurso exige reportlab. Instale: pip install "optimus-assistente[documentos]"'
        ) from erro
    largura = float(pagina.mediabox.width)
    altura = float(pagina.mediabox.height)
    buffer = BytesIO()
    tela = canvas.Canvas(buffer, pagesize=(largura, altura))
    if marca:
        tela.saveState()
        tela.setFillColor(Color(0.55, 0.55, 0.55, alpha=0.24))
        tela.translate(largura / 2, altura / 2)
        tela.rotate(35)
        tela.setFont("Helvetica-Bold", max(18, min(48, largura / 12)))
        tela.drawCentredString(0, 0, texto[:100])
        tela.restoreState()
    else:
        tela.setFillColor(Color(0, 0, 0, alpha=0.9))
        tela.setFont("Helvetica", 9)
        tela.drawCentredString(largura / 2, 18, texto[:80])
    tela.save()
    buffer.seek(0)
    pagina.merge_page(PdfReader(buffer).pages[0])


def _salvar_pdf(writer, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "wb") as arquivo:
        writer.write(arquivo)


@ferramenta(
    "pdf_info",
    "Mostra informações de um PDF: número de páginas, se tem texto, se está protegido, metadados.",
    {"arquivo": texto("Caminho do arquivo PDF")},
    grupo="pdf", risco=LIVRE,
)
def pdf_info(ctx, arquivo: str):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    try:
        leitor = PdfReader(str(caminho), strict=False)
        encriptado = leitor.is_encrypted
        paginas = len(leitor.pages) if not encriptado else 0
        tem_texto = False
        if not encriptado and paginas > 0:
            try:
                tem_texto = bool((leitor.pages[0].extract_text() or "").strip())
            except Exception:
                tem_texto = False
        meta = {}
        if leitor.metadata:
            for k, v in leitor.metadata.items():
                if v:
                    meta[str(k).lstrip("/")] = str(v)[:200]
        return {
            "arquivo": str(caminho),
            "paginas": paginas,
            "encriptado": encriptado,
            "tem_texto": tem_texto,
            "tamanho_bytes": caminho.stat().st_size,
            "metadados": meta,
        }
    except Exception as e:
        return {"erro": f"Não consegui ler o PDF: {e}"}


@ferramenta(
    "pdf_ler",
    "Extrai o texto de um PDF (páginas opcionais). PDFs escaneados precisam de OCR antes.",
    {"arquivo": texto("Caminho do PDF"),
     "paginas": texto("Páginas, ex.: 1-3,5 (vazio = todas)")},
    grupo="pdf", risco=LIVRE, obrigatorios=["arquivo"],
)
def pdf_ler(ctx, arquivo: str, paginas: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    try:
        leitor = PdfReader(str(caminho), strict=False)
        if leitor.is_encrypted:
            return {"erro": "PDF protegido por senha. Use pdf_desbloquear primeiro."}
        total = len(leitor.pages)
        idxs = _paginas_parse(paginas, total)
        textos = []
        for i in idxs:
            t = (leitor.pages[i].extract_text() or "").strip()
            textos.append({"pagina": i + 1, "texto": t[:15000]})
        junto = "\n\n".join(f"--- Página {p['pagina']} ---\n{p['texto']}" for p in textos if p["texto"])
        if not junto.strip():
            return {
                "aviso": "Nenhum texto extraído. Pode ser PDF escaneado. Use pdf_ocr.",
                "paginas_lidas": [p["pagina"] for p in textos],
                "texto": "",
            }
        return {"paginas_lidas": [p["pagina"] for p in textos], "texto": junto[:50000]}
    except Exception as e:
        return {"erro": f"Falha ao ler PDF: {e}"}


@ferramenta(
    "pdf_juntar",
    "Junta vários PDFs em um só arquivo.",
    {"arquivos": texto("Caminhos separados por vírgula ou ponto-e-vírgula"),
     "destino": texto("Arquivo de saída (padrão: juntos.pdf)")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivos"],
)
def pdf_juntar(ctx, arquivos: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    lista = [a.strip() for a in re.split(r"[,;]+", arquivos) if a.strip()]
    if len(lista) < 2:
        return {"erro": "Informe pelo menos dois PDFs para juntar."}
    writer = PdfWriter()
    usados = []
    for a in lista:
        p = _caminho(ctx, a)
        if not p.is_file():
            return {"erro": f"Não achei: {p}"}
        try:
            leitor = PdfReader(str(p), strict=False)
            if leitor.is_encrypted:
                return {"erro": f"PDF protegido: {p.name}. Desbloqueie antes."}
            for pagina in leitor.pages:
                writer.add_page(pagina)
            usados.append(str(p))
        except Exception as e:
            return {"erro": f"Erro em {p.name}: {e}"}
    out = _caminho(ctx, destino or "juntos.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return {"mensagem": f"Juntei {len(usados)} PDFs em {out.name}.", "destino": str(out), "arquivos": usados}


@ferramenta(
    "pdf_extrair",
    "Extrai páginas específicas de um PDF para um novo arquivo.",
    {"arquivo": texto("PDF de origem"),
     "paginas": texto("Páginas a extrair, ex.: 2-4,7"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "paginas"],
)
def pdf_extrair(ctx, arquivo: str, paginas: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido. Use pdf_desbloquear."}
    idxs = _paginas_parse(paginas, len(leitor.pages))
    if not idxs:
        return {"erro": "Nenhuma página válida informada."}
    writer = PdfWriter()
    for i in idxs:
        writer.add_page(leitor.pages[i])
    out = _caminho(ctx, destino or f"{caminho.stem}_paginas.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    return {"mensagem": f"Extraí {len(idxs)} página(s).", "destino": str(out), "paginas": [i+1 for i in idxs]}


@ferramenta(
    "pdf_remover",
    "Remove páginas de um PDF.",
    {"arquivo": texto("PDF"),
     "paginas": texto("Páginas a remover, ex.: 1,3-5"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "paginas"],
)
def pdf_remover(ctx, arquivo: str, paginas: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido."}
    remover = set(_paginas_parse(paginas, len(leitor.pages)))
    writer = PdfWriter()
    mantidas = []
    for i, pagina in enumerate(leitor.pages):
        if i not in remover:
            writer.add_page(pagina)
            mantidas.append(i + 1)
    out = _caminho(ctx, destino or f"{caminho.stem}_editado.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    return {"mensagem": f"Removi {len(remover)} página(s). Restaram {len(mantidas)}.", "destino": str(out)}


@ferramenta(
    "pdf_organizar",
    "Reordena as páginas de um PDF na ordem informada.",
    {"arquivo": texto("PDF"),
     "paginas": texto("Nova ordem, ex.: 3,1,2,4"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "paginas"],
)
def pdf_organizar(ctx, arquivo: str, paginas: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido."}
    idxs = _paginas_parse(paginas, len(leitor.pages))
    if not idxs:
        return {"erro": "Ordem de páginas inválida."}
    writer = PdfWriter()
    for i in idxs:
        writer.add_page(leitor.pages[i])
    out = _caminho(ctx, destino or f"{caminho.stem}_organizado.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    return {"mensagem": "Páginas reordenadas.", "destino": str(out), "ordem": [i+1 for i in idxs]}


@ferramenta(
    "pdf_dividir",
    "Divide um PDF em vários arquivos (a cada N páginas).",
    {"arquivo": texto("PDF"),
     "a_cada": numero("Quantidade de páginas por arquivo (padrão 1)"),
     "destino": texto("Pasta de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_dividir(ctx, arquivo: str, a_cada: int = 1, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido."}
    n = max(1, int(a_cada or 1))
    pasta = _caminho(ctx, destino or f"{caminho.stem}_partes")
    pasta.mkdir(parents=True, exist_ok=True)
    gerados = []
    for inicio in range(0, len(leitor.pages), n):
        writer = PdfWriter()
        for i in range(inicio, min(inicio + n, len(leitor.pages))):
            writer.add_page(leitor.pages[i])
        nome = pasta / f"{caminho.stem}_p{inicio+1:03d}-{min(inicio+n, len(leitor.pages)):03d}.pdf"
        with open(nome, "wb") as f:
            writer.write(f)
        gerados.append(str(nome))
    return {"mensagem": f"Dividi em {len(gerados)} arquivo(s).", "arquivos": gerados}


@ferramenta(
    "pdf_girar",
    "Gira páginas de um PDF (90, 180 ou 270 graus).",
    {"arquivo": texto("PDF"),
     "graus": numero("Ângulo: 90, 180 ou 270"),
     "paginas": texto("Páginas a girar (vazio = todas)"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_girar(ctx, arquivo: str, graus: int = 90, paginas: str = "", destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    graus = int(graus or 90) % 360
    if graus not in (90, 180, 270):
        return {"erro": "Use 90, 180 ou 270 graus."}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido."}
    idxs = set(_paginas_parse(paginas, len(leitor.pages))) if paginas else set(range(len(leitor.pages)))
    writer = PdfWriter()
    for i, pagina in enumerate(leitor.pages):
        if i in idxs:
            pagina.rotate(graus)
        writer.add_page(pagina)
    out = _caminho(ctx, destino or f"{caminho.stem}_girado.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    return {"mensagem": f"Girei {len(idxs)} página(s) em {graus}°.", "destino": str(out)}


@ferramenta(
    "pdf_proteger",
    "Protege um PDF com senha.",
    {"arquivo": texto("PDF"),
     "senha": texto("Senha"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "senha"],
)
def pdf_proteger(ctx, arquivo: str, senha: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "Já está protegido."}
    writer = PdfWriter()
    for p in leitor.pages:
        writer.add_page(p)
    writer.encrypt(senha)
    out = _caminho(ctx, destino or f"{caminho.stem}_protegido.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    return {"mensagem": "PDF protegido com senha.", "destino": str(out)}


@ferramenta(
    "pdf_desbloquear",
    "Remove a senha de um PDF.",
    {"arquivo": texto("PDF protegido"),
     "senha": texto("Senha atual"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "senha"],
)
def pdf_desbloquear(ctx, arquivo: str, senha: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if not leitor.is_encrypted:
        return {"erro": "O PDF não está protegido."}
    if not leitor.decrypt(senha):
        return {"erro": "Senha incorreta."}
    writer = PdfWriter()
    for p in leitor.pages:
        writer.add_page(p)
    out = _caminho(ctx, destino or f"{caminho.stem}_desbloqueado.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    return {"mensagem": "Senha removida.", "destino": str(out)}


@ferramenta(
    "pdf_comprimir",
    "Tenta reduzir o tamanho de um PDF.",
    {"arquivo": texto("PDF"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_comprimir(ctx, arquivo: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido. Desbloqueie antes."}
    writer = PdfWriter()
    for p in leitor.pages:
        writer.add_page(p)
    try:
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    except Exception:
        pass
    out = _caminho(ctx, destino or f"{caminho.stem}_menor.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    antes = caminho.stat().st_size
    depois = out.stat().st_size
    return {
        "mensagem": f"Tamanho: {antes} → {depois} bytes ({100*depois/max(antes,1):.0f}%).",
        "destino": str(out),
        "antes_bytes": antes,
        "depois_bytes": depois,
    }


@ferramenta(
    "pdf_marca",
    "Adiciona marca d'água de texto (metadado; visual plena recomenda reportlab).",
    {"arquivo": texto("PDF"),
     "texto": texto("Texto da marca"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "texto"],
)
def pdf_marca(ctx, arquivo: str, texto: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido."}
    writer = PdfWriter()
    try:
        for pagina in leitor.pages:
            _sobrepor_texto(pagina, texto, marca=True)
            writer.add_page(pagina)
    except RuntimeError as erro:
        return {"erro": str(erro)}
    writer.add_metadata({"/Watermark": texto[:100]})
    out = _caminho(ctx, destino or f"{caminho.stem}_marca.pdf")
    _salvar_pdf(writer, out)
    return {"mensagem": f"Marca d'água visual aplicada em {len(leitor.pages)} página(s).",
            "destino": str(out), "visual": True}


@ferramenta(
    "pdf_numeros",
    "Prepara numeração de páginas.",
    {"arquivo": texto("PDF"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_numeros(ctx, arquivo: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido."}
    writer = PdfWriter()
    try:
        for i, pagina in enumerate(leitor.pages, start=1):
            _sobrepor_texto(pagina, str(i), marca=False)
            writer.add_page(pagina)
    except RuntimeError as erro:
        return {"erro": str(erro)}
    out = _caminho(ctx, destino or f"{caminho.stem}_numerado.pdf")
    _salvar_pdf(writer, out)
    return {"mensagem": f"Numeração visível inserida em {len(leitor.pages)} página(s).",
            "destino": str(out), "paginas_numeradas": len(leitor.pages)}


@ferramenta(
    "pdf_assinar",
    "Carimbo visual de assinatura (texto). Não é certificado ICP-Brasil.",
    {"arquivo": texto("PDF"),
     "texto": texto("Nome da assinatura"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "texto"],
)
def pdf_assinar(ctx, arquivo: str, texto: str, destino: str = ""):
    return pdf_marca(ctx, arquivo=arquivo, texto=f"Assinado por: {texto}", destino=destino or "")


@ferramenta(
    "pdf_censurar",
    "Localiza termos sensíveis e marca o arquivo.",
    {"arquivo": texto("PDF"),
     "texto": texto("Termos separados por vírgula"),
     "destino": texto("Arquivo de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "texto"],
)
def pdf_censurar(ctx, arquivo: str, texto: str, destino: str = ""):
    err = _precisa_pypdf()
    if err:
        return err
    from pypdf import PdfReader, PdfWriter
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    termos = [t.strip() for t in texto.split(",") if t.strip()]
    if not termos:
        return {"erro": "Informe pelo menos um termo."}
    leitor = PdfReader(str(caminho), strict=False)
    if leitor.is_encrypted:
        return {"erro": "PDF protegido."}
    encontrados = []
    for i, pagina in enumerate(leitor.pages):
        t = (pagina.extract_text() or "")
        for termo in termos:
            if termo.lower() in t.lower():
                encontrados.append({"pagina": i + 1, "termo": termo})
    writer = PdfWriter()
    for p in leitor.pages:
        writer.add_page(p)
    writer.add_metadata({"/CensoredTerms": ",".join(termos)[:200]})
    out = _caminho(ctx, destino or f"{caminho.stem}_censurado.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    return {"mensagem": f"Marcado. {len(encontrados)} ocorrência(s).", "ocorrencias": encontrados[:50], "destino": str(out)}


@ferramenta(
    "pdf_comparar",
    "Compara o texto de dois PDFs.",
    {"arquivo_a": texto("Primeiro PDF"),
     "arquivo_b": texto("Segundo PDF")},
    grupo="pdf", risco=LIVRE, obrigatorios=["arquivo_a", "arquivo_b"],
)
def pdf_comparar(ctx, arquivo_a: str, arquivo_b: str):
    a = pdf_ler(ctx, arquivo=arquivo_a)
    b = pdf_ler(ctx, arquivo=arquivo_b)
    if "erro" in a:
        return a
    if "erro" in b:
        return b
    ta = (a.get("texto") or "").strip()
    tb = (b.get("texto") or "").strip()
    iguais = ta == tb
    return {"iguais": iguais, "tamanho_a": len(ta), "tamanho_b": len(tb),
            "mensagem": "Textos idênticos." if iguais else "Há diferenças no texto."}


@ferramenta(
    "pdf_ocr",
    "OCR em PDF escaneado (Tesseract + pypdfium2 + pytesseract).",
    {"arquivo": texto("PDF escaneado"),
     "idioma": texto("Código Tesseract (por, eng...)"),
     "destino": texto("Saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_ocr(ctx, arquivo: str, idioma: str = "por", destino: str = ""):
    try:
        import pytesseract
        from pypdfium2 import PdfDocument
    except ImportError:
        return {"erro": "OCR precisa de: pip install pypdfium2 pytesseract e Tesseract no sistema."}
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    try:
        doc = PdfDocument(str(caminho))
        textos = []
        for i in range(len(doc)):
            page = doc[i]
            bitmap = page.render(scale=2).to_pil()
            t = pytesseract.image_to_string(bitmap, lang=idioma or "por")
            textos.append(f"--- Página {i+1} ---\n{t.strip()}")
        texto_final = "\n\n".join(textos)
        out_txt = _caminho(ctx, destino or f"{caminho.stem}_ocr.txt")
        if not str(out_txt).lower().endswith(".txt"):
            out_txt = out_txt.with_suffix(".txt")
        out_txt.write_text(texto_final, encoding="utf-8")
        return {"mensagem": f"OCR concluído ({len(doc)} páginas).", "texto": texto_final[:30000],
                "arquivo_texto": str(out_txt)}
    except Exception as e:
        return {"erro": f"Falha no OCR: {e}"}


@ferramenta(
    "pdf_converter",
    "Converte PDF para HTML/txt/csv ou Office→PDF via LibreOffice.",
    {"arquivo": texto("Arquivo"),
     "formato": texto("html|txt|docx|csv|pdf"),
     "destino": texto("Saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "formato"],
)
def pdf_converter(ctx, arquivo: str, formato: str, destino: str = ""):
    formato = (formato or "").lower().strip().lstrip(".")
    caminho = _caminho(ctx, arquivo)
    if not caminho.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    if caminho.suffix.lower() in (".doc", ".docx", ".odt", ".ppt", ".pptx", ".xls", ".xlsx") and formato == "pdf":
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            return {"erro": "LibreOffice (soffice) não encontrado."}
        pasta = caminho.parent
        try:
            subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pasta), str(caminho)],
                           check=True, timeout=120, capture_output=True)
            gerado = pasta / f"{caminho.stem}.pdf"
            if destino:
                out = _caminho(ctx, destino)
                shutil.move(str(gerado), str(out))
                gerado = out
            return {"mensagem": "Convertido via LibreOffice.", "destino": str(gerado)}
        except Exception as e:
            return {"erro": f"Falha no LibreOffice: {e}"}
    if formato in ("txt", "html", "docx", "csv"):
        lido = pdf_ler(ctx, arquivo=str(caminho))
        if "erro" in lido:
            return lido
        texto_pdf = lido.get("texto") or ""
        out = _caminho(ctx, destino or f"{caminho.stem}.{formato}")
        if formato == "txt":
            out.write_text(texto_pdf, encoding="utf-8")
        elif formato == "html":
            out.write_text(f"<html><body><pre>{texto_pdf.replace('<','<')}</pre></body></html>", encoding="utf-8")
        elif formato == "csv":
            linhas = [l.replace('"', '""') for l in texto_pdf.splitlines() if l.strip()]
            out.write_text("\n".join(f'"{l}"' for l in linhas), encoding="utf-8")
        else:
            out = out.with_suffix(".txt")
            out.write_text(texto_pdf, encoding="utf-8")
            return {"mensagem": "Texto extraído (DOCX completo requer python-docx).", "destino": str(out)}
        return {"mensagem": f"Convertido para {formato}.", "destino": str(out)}
    return {"erro": f"Formato '{formato}' não suportado. Use html, txt, csv ou pdf."}


@ferramenta(
    "pdf_resumir",
    "Extrai o texto do PDF para o modelo resumir/traduzir.",
    {"arquivo": texto("PDF"),
     "paginas": texto("Páginas (opcional)")},
    grupo="pdf", risco=LIVRE, obrigatorios=["arquivo"],
)
def pdf_resumir(ctx, arquivo: str, paginas: str = ""):
    return pdf_ler(ctx, arquivo=arquivo, paginas=paginas)
