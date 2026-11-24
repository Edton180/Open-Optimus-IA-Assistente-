"""Ferramentas adicionais de PDF para paridade local com suítes comerciais.

Todas as operações são executadas localmente. Dependências opcionais são verificadas
no momento do uso para que a instalação básica do Optimus continue leve.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, numero, texto


def _path(ctx, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and ctx and getattr(ctx, "pasta_trabalho", None):
        path = Path(ctx.pasta_trabalho) / path
    return path.resolve()


def _pypdf():
    try:
        from pypdf import PdfReader, PdfWriter
        return PdfReader, PdfWriter
    except ImportError:
        return None


@ferramenta(
    "pdf_imagens_para_pdf",
    "Converte imagens JPG, JPEG, PNG, TIFF ou BMP em PDF, uma imagem por página.",
    {"arquivos": texto("Caminhos separados por vírgula ou ponto-e-vírgula"),
     "destino": texto("PDF de saída"), "orientacao": texto("auto|retrato|paisagem"),
     "margem": numero("Margem em pontos (padrão 24)"),
     "modo": texto("original|documento|preto_branco") },
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivos"],
)
def pdf_imagens_para_pdf(ctx, arquivos: str, destino: str = "",
                         orientacao: str = "auto", margem: int = 24,
                         modo: str = "original"):
    try:
        from PIL import Image, ImageOps, ImageEnhance
        from reportlab.lib.pagesizes import A4, landscape, portrait
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except ImportError:
        return {"erro": 'Conversão de imagens requer Pillow e reportlab. Instale: pip install "optimus-assistente[pdf]"'}
    import re
    lista = [x.strip().strip('"') for x in re.split(r"[,;]+", arquivos) if x.strip()]
    if not lista:
        return {"erro": "Informe ao menos uma imagem."}
    modo = (modo or "original").lower()
    if modo not in ("original", "documento", "preto_branco"):
        return {"erro": "Modo deve ser original, documento ou preto_branco."}
    imagens = []
    for nome in lista:
        p = _path(ctx, nome)
        if not p.is_file():
            return {"erro": f"Imagem não encontrada: {p}"}
        try:
            with Image.open(p) as img:
                preparada = img.convert("RGB").copy()
                if modo in ("documento", "preto_branco"):
                    preparada = ImageOps.autocontrast(preparada.convert("L"))
                    preparada = ImageEnhance.Sharpness(preparada).enhance(1.5)
                if modo == "preto_branco":
                    preparada = preparada.point(lambda pixel: 255 if pixel > 170 else 0)
                imagens.append(preparada.convert("RGB"))
        except Exception as exc:
            return {"erro": f"Não consegui abrir {p.name}: {exc}"}
    out = _path(ctx, destino or f"{_path(ctx, lista[0]).stem}_imagens.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    margem_pt = max(0, min(int(margem or 24), 144))
    try:
        temp = out.with_name(out.name + ".tmp")
        c = canvas.Canvas(str(temp))
        for img in imagens:
            w, h = A4
            orientacao_pagina = (orientacao or "auto").lower()
            if orientacao_pagina == "paisagem" or (orientacao_pagina == "auto" and img.width > img.height):
                w, h = landscape(A4)
            else:
                w, h = portrait(A4)
            c.setPageSize((w, h))
            escala = min((w - 2*margem_pt) / img.width, (h - 2*margem_pt) / img.height)
            iw, ih = img.width * escala, img.height * escala
            c.drawImage(ImageReader(img), (w-iw)/2, (h-ih)/2, iw, ih, preserveAspectRatio=True)
            c.showPage()
        c.save()
        temp.replace(out)
    except Exception as exc:
        return {"erro": f"Falha ao gerar PDF: {exc}"}
    return {"mensagem": f"Criei PDF com {len(imagens)} imagem(ns).", "destino": str(out),
            "paginas": len(imagens), "tamanho_bytes": out.stat().st_size, "modo": modo}


@ferramenta(
    "pdf_para_imagens",
    "Renderiza cada página de um PDF como PNG ou JPG e entrega também um ZIP.",
    {"arquivo": texto("PDF de origem"), "formato": texto("png|jpg"),
     "escala": numero("Escala de renderização (1 a 4; padrão 2)"),
     "destino": texto("Pasta ou arquivo ZIP de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_para_imagens(ctx, arquivo: str, formato: str = "jpg", escala: int = 2,
                     destino: str = ""):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return {"erro": "Renderização requer pypdfium2 e Pillow. Instale: pip install \"optimus-assistente[pdf]\""}
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    formato = (formato or "jpg").lower().lstrip(".")
    if formato not in ("jpg", "jpeg", "png"):
        return {"erro": "Formato deve ser jpg ou png."}
    fator = max(1, min(int(escala or 2), 4))
    pasta = _path(ctx, destino or f"{origem.stem}_imagens")
    if pasta.suffix.lower() == ".zip":
        zip_path = pasta
        pasta = zip_path.with_suffix("")
    else:
        zip_path = pasta.with_suffix(".zip")
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        doc = pdfium.PdfDocument(str(origem))
        gerados = []
        for i in range(len(doc)):
            bitmap = doc[i].render(scale=fator)
            imagem = bitmap.to_pil()
            nome = pasta / f"{origem.stem}_pagina_{i+1:04d}.{formato}"
            imagem.save(nome, format="PNG" if formato == "png" else "JPEG", quality=92)
            gerados.append(nome)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
            for item in gerados:
                pacote.write(item, item.name)
        return {"mensagem": f"Renderizei {len(gerados)} página(s).", "pasta": str(pasta),
                "zip": str(zip_path), "arquivos": [str(x) for x in gerados]}
    except Exception as exc:
        return {"erro": f"Falha ao renderizar PDF: {exc}"}


@ferramenta(
    "pdf_cortar",
    "Corta a área visível de páginas PDF usando margens em pontos.",
    {"arquivo": texto("PDF"), "esquerda": numero("Margem esquerda em pontos"),
     "inferior": numero("Margem inferior em pontos"), "direita": numero("Margem direita em pontos"),
     "superior": numero("Margem superior em pontos"), "paginas": texto("Páginas (vazio = todas)"),
     "destino": texto("PDF de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_cortar(ctx, arquivo: str, esquerda: int = 0, inferior: int = 0,
               direita: int = 0, superior: int = 0, paginas: str = "", destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, PdfWriter = deps
    from pypdf.generic import RectangleObject
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    try:
        reader = PdfReader(str(origem), strict=False)
        if reader.is_encrypted:
            return {"erro": "PDF protegido; desbloqueie antes."}
        total = len(reader.pages)
        escolhidas = set(range(total))
        if paginas.strip():
            escolhidas = set()
            for item in paginas.replace(" ", "").split(","):
                if "-" in item:
                    a, b = (int(x) for x in item.split("-", 1))
                    escolhidas.update(range(max(1, min(a,b))-1, min(total, max(a,b))))
                elif item.isdigit() and 1 <= int(item) <= total:
                    escolhidas.add(int(item)-1)
        margens = [max(0, int(x or 0)) for x in (esquerda, inferior, direita, superior)]
        writer = PdfWriter()
        for i, page in enumerate(reader.pages):
            if i in escolhidas:
                box = page.cropbox
                x0, y0, x1, y1 = map(float, (box.left, box.bottom, box.right, box.top))
                nx0, ny0 = x0 + margens[0], y0 + margens[1]
                nx1, ny1 = x1 - margens[2], y1 - margens[3]
                if nx1 <= nx0 or ny1 <= ny0:
                    return {"erro": f"As margens deixam a página {i+1} sem área visível."}
                page.cropbox = RectangleObject((nx0, ny0, nx1, ny1))
            writer.add_page(page)
        out = _path(ctx, destino or f"{origem.stem}_cortado.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_name(out.name + ".tmp")
        with temp.open("wb") as f:
            writer.write(f)
        temp.replace(out)
        return {"mensagem": f"Área visível ajustada em {len(escolhidas)} página(s).",
                "destino": str(out), "paginas": sorted(i+1 for i in escolhidas)}
    except Exception as exc:
        return {"erro": f"Falha ao cortar PDF: {exc}"}


@ferramenta(
    "pdf_metadados",
    "Exibe, altera ou remove metadados de um PDF.",
    {"arquivo": texto("PDF"), "acao": texto("ler|remover|definir"),
     "metadados": texto("JSON com campos title, author, subject, keywords, creator"),
     "destino": texto("PDF de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_metadados(ctx, arquivo: str, acao: str = "ler", metadados: str = "", destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, PdfWriter = deps
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    try:
        reader = PdfReader(str(origem), strict=False)
        atual = {str(k).lstrip("/"): str(v) for k, v in (reader.metadata or {}).items() if v}
        acao = (acao or "ler").lower()
        if acao == "ler":
            return {"metadados": atual}
        if reader.is_encrypted:
            return {"erro": "PDF protegido; desbloqueie antes."}
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        if acao == "remover":
            novos = {}
        elif acao == "definir":
            novos = json.loads(metadados or "{}")
            if not isinstance(novos, dict):
                return {"erro": "metadados deve ser um objeto JSON."}
        else:
            return {"erro": "Ação deve ser ler, remover ou definir."}
        writer.add_metadata({f"/{k}": str(v) for k, v in novos.items() if k in
                             ("title", "author", "subject", "keywords", "creator", "producer")})
        out = _path(ctx, destino or f"{origem.stem}_metadados.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("wb") as f:
            writer.write(f)
        return {"mensagem": "Metadados atualizados.", "destino": str(out),
                "metadados_anteriores": atual, "metadados_novos": novos}
    except Exception as exc:
        return {"erro": f"Falha ao processar metadados: {exc}"}


@ferramenta(
    "pdf_reparar",
    "Tenta reconstruir a estrutura de um PDF danificado e valida o arquivo resultante.",
    {"arquivo": texto("PDF danificado"), "destino": texto("PDF reparado")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_reparar(ctx, arquivo: str, destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, PdfWriter = deps
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    out = _path(ctx, destino or f"{origem.stem}_reparado.pdf")
    temp = out.with_name(out.name + ".tmp")
    try:
        reader = PdfReader(str(origem), strict=False)
        if reader.is_encrypted:
            return {"erro": "PDF protegido; desbloqueie antes."}
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        if reader.metadata:
            writer.add_metadata({str(k): str(v) for k, v in reader.metadata.items() if v})
        out.parent.mkdir(parents=True, exist_ok=True)
        with temp.open("wb") as f:
            writer.write(f)
        check = PdfReader(str(temp), strict=True)
        if len(check.pages) != len(reader.pages):
            temp.unlink(missing_ok=True)
            return {"erro": "A validação encontrou perda de páginas; original preservado."}
        temp.replace(out)
        return {"mensagem": "Estrutura reconstruída e validada.", "destino": str(out),
                "paginas": len(check.pages), "tamanho_bytes": out.stat().st_size,
                "observacao": "Recuperação best-effort; objetos corrompidos ou dados perdidos não podem ser garantidos."}
    except Exception as exc:
        temp.unlink(missing_ok=True)
        return {"erro": f"Não foi possível reparar automaticamente: {exc}. Original preservado."}


@ferramenta(
    "pdf_para_markdown",
    "Extrai o texto de um PDF para Markdown, separando as páginas.",
    {"arquivo": texto("PDF"), "destino": texto("Arquivo .md")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_para_markdown(ctx, arquivo: str, destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, _ = deps
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    try:
        reader = PdfReader(str(origem), strict=False)
        if reader.is_encrypted:
            return {"erro": "PDF protegido; desbloqueie antes."}
        partes = [f"# {origem.stem}\n"]
        for i, page in enumerate(reader.pages, 1):
            conteudo = (page.extract_text() or "").strip()
            partes.append(f"\n## Página {i}\n\n{conteudo or '_Sem texto extraível nesta página._'}")
        out = _path(ctx, destino or f"{origem.stem}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(partes), encoding="utf-8")
        return {"mensagem": "Markdown gerado.", "destino": str(out), "paginas": len(reader.pages)}
    except Exception as exc:
        return {"erro": f"Falha ao converter para Markdown: {exc}"}


@ferramenta(
    "pdf_html_para_pdf",
    "Converte um arquivo HTML local para PDF usando LibreOffice instalado no computador.",
    {"arquivo": texto("Arquivo HTML local"), "destino": texto("PDF de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_html_para_pdf(ctx, arquivo: str, destino: str = ""):
    origem = _path(ctx, arquivo)
    if not origem.is_file() or origem.suffix.lower() not in (".html", ".htm"):
        return {"erro": "Informe um arquivo .html ou .htm local existente."}
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return {"erro": "HTML para PDF requer LibreOffice (soffice) instalado."}
    out = _path(ctx, destino or f"{origem.stem}.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir",
                        str(out.parent), str(origem)], check=True, timeout=120,
                       capture_output=True)
        gerado = out.parent / f"{origem.stem}.pdf"
        if not gerado.is_file() or gerado.stat().st_size == 0:
            return {"erro": "LibreOffice não gerou um PDF válido."}
        if gerado.resolve() != out.resolve():
            gerado.replace(out)
        deps = _pypdf()
        if deps and len(deps[0](str(out)).pages) < 1:
            out.unlink(missing_ok=True)
            return {"erro": "O PDF gerado não passou na validação."}
        return {"mensagem": "HTML convertido para PDF.", "destino": str(out)}
    except Exception as exc:
        return {"erro": f"Falha ao converter HTML: {exc}"}


@ferramenta(
    "pdf_formularios",
    "Lista campos de formulário PDF ou preenche campos existentes a partir de um JSON.",
    {"arquivo": texto("PDF"), "valores": texto("JSON campo: valor (vazio = apenas listar)"),
     "destino": texto("PDF preenchido")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_formularios(ctx, arquivo: str, valores: str = "", destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, PdfWriter = deps
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    try:
        reader = PdfReader(str(origem), strict=False)
        if reader.is_encrypted:
            return {"erro": "PDF protegido; desbloqueie antes."}
        campos = reader.get_fields() or {}
        nomes = {nome: str(campo.get("/FT", "")) for nome, campo in campos.items()}
        if not valores.strip():
            return {"campos": nomes, "total": len(nomes)}
        dados = json.loads(valores)
        if not isinstance(dados, dict):
            return {"erro": "valores deve ser um objeto JSON."}
        desconhecidos = sorted(set(dados) - set(nomes))
        if desconhecidos:
            return {"erro": "Campos inexistentes: " + ", ".join(desconhecidos),
                    "campos_disponiveis": list(nomes)}
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        for page in writer.pages:
            writer.update_page_form_field_values(page, {str(k): str(v) for k, v in dados.items()},
                                                 auto_regenerate=False)
        out = _path(ctx, destino or f"{origem.stem}_preenchido.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("wb") as f:
            writer.write(f)
        return {"mensagem": "Formulário preenchido.", "destino": str(out),
                "campos_preenchidos": list(dados)}
    except Exception as exc:
        return {"erro": f"Falha ao processar formulário PDF: {exc}"}


@ferramenta(
    "pdf_para_excel",
    "Extrai tabelas de um PDF para XLSX; quando não há tabelas detectáveis, exporta o texto por página.",
    {"arquivo": texto("PDF de origem"), "destino": texto("Planilha XLSX")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_para_excel(ctx, arquivo: str, destino: str = ""):
    try:
        import pdfplumber
        from openpyxl import Workbook
    except ImportError:
        return {"erro": 'Exportação para Excel requer pdfplumber e openpyxl. Instale: pip install "optimus-assistente[pdf]"'}
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    try:
        workbook = Workbook()
        resumo = workbook.active
        resumo.title = "Conteudo"
        tabelas = 0
        paginas_ocr = []
        doc_ocr = None
        with pdfplumber.open(str(origem)) as pdf:
            for numero_pagina, page in enumerate(pdf.pages, 1):
                achadas = page.extract_tables() or []
                for indice, tabela in enumerate(achadas, 1):
                    tabelas += 1
                    sheet = workbook.create_sheet(f"P{numero_pagina}_T{indice}"[:31])
                    for linha in tabela:
                        sheet.append([celula or "" for celula in linha])
                texto_pagina = page.extract_text() or ""
                if not texto_pagina.strip() and not achadas:
                    try:
                        import pypdfium2 as pdfium
                        import pytesseract
                        if doc_ocr is None:
                            doc_ocr = pdfium.PdfDocument(str(origem))
                        imagem = doc_ocr[numero_pagina-1].render(scale=2).to_pil()
                        texto_pagina = pytesseract.image_to_string(imagem, lang="por").strip()
                        if texto_pagina:
                            paginas_ocr.append(numero_pagina)
                    except ImportError:
                        pass
                if texto_pagina:
                    resumo.append([f"Página {numero_pagina}"])
                    for linha in texto_pagina.splitlines():
                        resumo.append([linha])
        out = _path(ctx, destino or f"{origem.stem}.xlsx")
        if out.suffix.lower() != ".xlsx":
            out = out.with_suffix(".xlsx")
        out.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(out)
        return {"mensagem": "Conteúdo exportado para Excel.",
                "destino": str(out), "tabelas_detectadas": tabelas, "paginas_processadas_por_ocr": paginas_ocr,
                "observacao": "Tabelas detectadas são aproximadas; OCR de páginas escaneadas exporta texto por linha, não reconstrói tabelas complexas."}
    except Exception as exc:
        return {"erro": f"Falha ao exportar Excel: {exc}"}


@ferramenta(
    "pdf_para_powerpoint",
    "Converte cada página de PDF em um slide de PowerPoint visual (páginas como imagens).",
    {"arquivo": texto("PDF de origem"), "destino": texto("Apresentação PPTX"),
     "escala": numero("Escala de renderização (1 a 3)")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_para_powerpoint(ctx, arquivo: str, destino: str = "", escala: int = 2):
    try:
        import pypdfium2 as pdfium
        from pptx import Presentation
        from pptx.util import Inches
        from io import BytesIO
    except ImportError:
        return {"erro": 'Exportação para PowerPoint requer pypdfium2 e python-pptx. Instale: pip install "optimus-assistente[pdf]"'}
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    fator = max(1, min(int(escala or 2), 3))
    try:
        doc = pdfium.PdfDocument(str(origem))
        if len(doc) == 0:
            return {"erro": "PDF sem páginas."}
        primeira = doc[0]
        largura, altura = primeira.get_size()
        proporcao = largura / altura if altura else 1.414
        prs = Presentation()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(10 / proporcao)
        layout = prs.slide_layouts[6]
        for pagina in doc:
            imagem = pagina.render(scale=fator).to_pil()
            buffer = BytesIO()
            imagem.save(buffer, format="PNG")
            buffer.seek(0)
            slide = prs.slides.add_slide(layout)
            slide.shapes.add_picture(buffer, 0, 0, width=prs.slide_width, height=prs.slide_height)
        out = _path(ctx, destino or f"{origem.stem}.pptx")
        if out.suffix.lower() != ".pptx":
            out = out.with_suffix(".pptx")
        out.parent.mkdir(parents=True, exist_ok=True)
        prs.save(out)
        return {"mensagem": f"Apresentação criada com {len(doc)} slides.",
                "destino": str(out),
                "observacao": "Cada slide contém a página original como imagem; o texto não fica editável."}
    except Exception as exc:
        return {"erro": f"Falha ao converter para PowerPoint: {exc}"}


@ferramenta(
    "pdf_comparar_visual",
    "Compara visualmente dois PDFs, gera imagens de diferença por página e um ZIP.",
    {"arquivo_a": texto("Primeiro PDF"), "arquivo_b": texto("Segundo PDF"),
     "destino": texto("ZIP de diferenças")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo_a", "arquivo_b"],
)
def pdf_comparar_visual(ctx, arquivo_a: str, arquivo_b: str, destino: str = ""):
    try:
        import pypdfium2 as pdfium
        from PIL import Image, ImageChops, ImageEnhance
    except ImportError:
        return {"erro": 'Comparação visual requer pypdfium2 e Pillow. Instale: pip install "optimus-assistente[pdf]"'}
    a, b = _path(ctx, arquivo_a), _path(ctx, arquivo_b)
    if not a.is_file() or not b.is_file():
        return {"erro": "Não encontrei os dois PDFs."}
    pasta = _path(ctx, f"{a.stem}_vs_{b.stem}_diff")
    zip_path = _path(ctx, destino or f"{a.stem}_vs_{b.stem}_diff.zip")
    try:
        da, db = pdfium.PdfDocument(str(a)), pdfium.PdfDocument(str(b))
        pasta.mkdir(parents=True, exist_ok=True)
        quantidade = max(len(da), len(db))
        arquivos = []
        for i in range(quantidade):
            if i >= len(da) or i >= len(db):
                continue
            ia = da[i].render(scale=1.5).to_pil().convert("RGB")
            ib = db[i].render(scale=1.5).to_pil().convert("RGB")
            if ia.size != ib.size:
                ib = ib.resize(ia.size)
            diff = ImageChops.difference(ia, ib)
            diff = ImageEnhance.Contrast(diff).enhance(3)
            nome = pasta / f"pagina_{i+1:04d}_diff.png"
            diff.save(nome)
            arquivos.append(nome)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
            for item in arquivos:
                pacote.write(item, item.name)
        return {"mensagem": "Comparação visual concluída.",
                "paginas_pdf_a": len(da), "paginas_pdf_b": len(db),
                "paginas_comparadas": len(arquivos), "zip": str(zip_path),
                "observacao": "Diferenças são realçadas por imagem; páginas ausentes são reportadas pela contagem."}
    except Exception as exc:
        return {"erro": f"Falha na comparação visual: {exc}"}


@ferramenta(
    "pdf_editar",
    "Insere texto, retângulo, círculo ou imagem sobre páginas PDF em coordenadas de pontos.",
    {"arquivo": texto("PDF de origem"), "tipo": texto("texto|retangulo|circulo|imagem"),
     "conteudo": texto("Texto ou caminho da imagem"),
     "x": numero("Posição X em pontos a partir da esquerda"),
     "y": numero("Posição Y em pontos a partir da base"),
     "largura": numero("Largura em pontos"), "altura": numero("Altura em pontos"),
     "pagina": numero("Página 1-based; 0 aplica em todas"),
     "destino": texto("PDF de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "tipo"],
)
def pdf_editar(ctx, arquivo: str, tipo: str, conteudo: str = "", x: int = 72, y: int = 72,
               largura: int = 180, altura: int = 48, pagina: int = 1, destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    try:
        from io import BytesIO
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        PdfReader, PdfWriter = deps
        origem = _path(ctx, arquivo)
        if not origem.is_file():
            return {"erro": f"PDF não encontrado: {origem}"}
        tipo = (tipo or "").lower()
        if tipo not in ("texto", "retangulo", "circulo", "imagem"):
            return {"erro": "Tipo deve ser texto, retangulo, circulo ou imagem."}
        imagem = None
        if tipo == "imagem":
            imagem = _path(ctx, conteudo)
            if not imagem.is_file():
                return {"erro": f"Imagem não encontrada: {imagem}"}
        reader = PdfReader(str(origem), strict=False)
        if reader.is_encrypted:
            return {"erro": "PDF protegido; desbloqueie antes."}
        if pagina < 0 or pagina > len(reader.pages):
            return {"erro": "Página inválida."}
        writer = PdfWriter()
        aplicadas = 0
        for indice, page in enumerate(reader.pages, 1):
            if pagina not in (0, indice):
                writer.add_page(page)
                continue
            w, h = float(page.mediabox.width), float(page.mediabox.height)
            buffer = BytesIO()
            layer = canvas.Canvas(buffer, pagesize=(w, h))
            if tipo == "texto":
                layer.setFont("Helvetica", 12)
                layer.drawString(max(0, x), max(0, y), (conteudo or "")[:500])
            elif tipo == "retangulo":
                layer.rect(max(0, x), max(0, y), max(1, min(largura, w)),
                           max(1, min(altura, h)), stroke=1, fill=0)
            elif tipo == "circulo":
                layer.ellipse(max(0, x), max(0, y), max(0, x)+max(1, largura),
                              max(0, y)+max(1, altura), stroke=1, fill=0)
            else:
                layer.drawImage(ImageReader(str(imagem)), max(0, x), max(0, y),
                                width=max(1, min(largura, w)),
                                height=max(1, min(altura, h)), preserveAspectRatio=True,
                                anchor="c", mask="auto")
            layer.save()
            buffer.seek(0)
            writer.add_page(page)
            writer.pages[-1].merge_page(PdfReader(buffer).pages[0])
            aplicadas += 1
        out = _path(ctx, destino or f"{origem.stem}_editado.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_name(out.name + ".tmp")
        with temp.open("wb") as arquivo_saida:
            writer.write(arquivo_saida)
        if len(PdfReader(str(temp), strict=True).pages) != len(reader.pages):
            temp.unlink(missing_ok=True)
            return {"erro": "Validação falhou; arquivo original preservado."}
        temp.replace(out)
        return {"mensagem": f"Elemento inserido em {aplicadas} página(s).",
                "destino": str(out),
                "observacao": "Este editor insere elementos sobre a página; não reescreve o texto original nem oferece editor visual drag-and-drop."}
    except Exception as exc:
        return {"erro": f"Falha ao editar PDF: {exc}"}


@ferramenta(
    "pdf_assinar_digital",
    "Assina criptograficamente um PDF usando certificado PKCS#12 (.p12/.pfx) e chave privada local.",
    {"arquivo": texto("PDF de origem"), "certificado": texto("Caminho do certificado .p12 ou .pfx"),
     "senha": texto("Senha do certificado"), "campo": texto("Nome do campo de assinatura"),
     "destino": texto("PDF assinado")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "certificado", "senha"],
)
def pdf_assinar_digital(ctx, arquivo: str, certificado: str, senha: str,
                        campo: str = "AssinaturaOptimus", destino: str = ""):
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
    except ImportError:
        return {"erro": 'Assinatura digital requer pyHanko. Instale: pip install "optimus-assistente[pdf]"'}
    origem, pfx = _path(ctx, arquivo), _path(ctx, certificado)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    if not pfx.is_file() or pfx.suffix.lower() not in (".p12", ".pfx"):
        return {"erro": "Informe um certificado PKCS#12 .p12 ou .pfx válido."}
    if not senha:
        return {"erro": "A senha do certificado é obrigatória."}
    out = _path(ctx, destino or f"{origem.stem}_assinado.pdf")
    temp = out.with_name(out.name + ".tmp")
    try:
        signer = signers.SimpleSigner.load_pkcs12(str(pfx), passphrase=senha.encode("utf-8"))
        if signer is None:
            return {"erro": "Não foi possível carregar a chave e o certificado. Confira arquivo e senha."}
        out.parent.mkdir(parents=True, exist_ok=True)
        with origem.open("rb") as entrada, temp.open("wb") as saida:
            writer = IncrementalPdfFileWriter(entrada)
            assinatura = signers.PdfSigner(
                signers.PdfSignatureMetadata(field_name=(campo or "AssinaturaOptimus")[:80]),
                signer=signer,
            )
            assinatura.sign_pdf(writer, output=saida)
        from pypdf import PdfReader
        validacao = PdfReader(str(temp), strict=True)
        campos = validacao.get_fields() or {}
        assinados = [nome for nome, valor in campos.items()
                     if str(valor.get("/FT", "")) == "/Sig" and valor.get("/V")]
        if not assinados:
            temp.unlink(missing_ok=True)
            return {"erro": "A saída não contém campo de assinatura preenchido; original preservado."}
        temp.replace(out)
        return {
            "mensagem": "Assinatura criptográfica incorporada ao PDF.",
            "destino": str(out), "campos_assinados": assinados,
            "observacao": "A integridade criptográfica foi conferida estruturalmente. A confiança da cadeia, revogação e validade jurídica dependem da autoridade certificadora e da validação do destinatário. Não é garantia automática de conformidade ICP-Brasil."
        }
    except Exception as exc:
        temp.unlink(missing_ok=True)
        return {"erro": f"Falha na assinatura digital: {exc}. O PDF original foi preservado."}


def censurar_por_rasterizacao(ctx, arquivo: str, texto: str, destino: str = "",
                              idioma: str = "por", escala: int = 3):
    """Redação OCR: rasteriza todas as páginas, cobre ocorrências e descarta os objetos originais."""
    try:
        import re
        from io import BytesIO
        import pytesseract
        import pypdfium2 as pdfium
        from PIL import ImageDraw
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
        from pypdf import PdfReader
    except ImportError:
        return {"erro": "Censura segura requer pytesseract, Tesseract no sistema, pypdfium2, Pillow e reportlab."}
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    termos = [t.strip() for t in re.split(r"[,;]+", texto or "") if t.strip()]
    normalizar = lambda valor: re.sub(r"[^a-z0-9]", "", valor.casefold())
    termos_norm = [(termo, normalizar(termo)) for termo in termos]
    termos_norm = [(termo, termo_norm) for termo, termo_norm in termos_norm if termo_norm]
    if not termos_norm:
        return {"erro": "Informe termos válidos para censurar."}
    fator = max(2, min(int(escala or 3), 5))
    out = _path(ctx, destino or f"{origem.stem}_censurado.pdf")
    temp = out.with_name(out.name + ".tmp")
    try:
        doc = pdfium.PdfDocument(str(origem))
        buffer_pdf = BytesIO()
        pdf_saida = canvas.Canvas(buffer_pdf)
        paginas_com_ocorrencia = set()
        total_ocorrencias = 0
        for numero, page in enumerate(doc, 1):
            imagem = page.render(scale=fator).to_pil().convert("RGB")
            dados = pytesseract.image_to_data(
                imagem, lang=idioma or "por", output_type=pytesseract.Output.DICT
            )
            palavras = []
            for indice, bruto in enumerate(dados.get("text", [])):
                palavra = normalizar(bruto)
                if not palavra:
                    continue
                try:
                    x, y = int(dados["left"][indice]), int(dados["top"][indice])
                    w, h = int(dados["width"][indice]), int(dados["height"][indice])
                except (KeyError, ValueError, TypeError, IndexError):
                    continue
                if w > 0 and h > 0:
                    palavras.append((palavra, x, y, x+w, y+h))
            texto_junto = "".join(item[0] for item in palavras)
            caixas = []
            for termo_original, termo in termos_norm:
                inicio = 0
                while True:
                    pos = texto_junto.find(termo, inicio)
                    if pos < 0:
                        break
                    fim = pos + len(termo)
                    cursor = 0
                    selecionadas = []
                    for palavra, x0, y0, x1, y1 in palavras:
                        proximo = cursor + len(palavra)
                        if cursor < fim and proximo > pos:
                            selecionadas.append((x0, y0, x1, y1))
                        cursor = proximo
                    if selecionadas:
                        margem = 8
                        caixa = (
                            max(0, min(x[0] for x in selecionadas)-margem),
                            max(0, min(x[1] for x in selecionadas)-margem),
                            min(imagem.width, max(x[2] for x in selecionadas)+margem),
                            min(imagem.height, max(x[3] for x in selecionadas)+margem),
                        )
                        caixas.append(caixa)
                        paginas_com_ocorrencia.add(numero)
                        total_ocorrencias += 1
                    inicio = fim
            if caixas:
                desenho = ImageDraw.Draw(imagem)
                for caixa in caixas:
                    desenho.rectangle(caixa, fill="black")
            # Verificar todas as páginas, inclusive aquelas em que a primeira passada não detectou
            # o termo. Se o OCR ainda encontrar qualquer alvo, a operação inteira é abortada.
            depois = pytesseract.image_to_data(
                imagem, lang=idioma or "por", output_type=pytesseract.Output.DICT
            )
            texto_depois = "".join(normalizar(x) for x in depois.get("text", []))
            if any(termo in texto_depois for _, termo in termos_norm):
                temp.unlink(missing_ok=True)
                return {"erro": f"Não consegui confirmar a remoção OCR na página {numero}; nenhum resultado foi salvo."}
            largura_pt = imagem.width * 72 / (72 * fator)
            altura_pt = imagem.height * 72 / (72 * fator)
            pdf_saida.setPageSize((largura_pt, altura_pt))
            pdf_saida.drawImage(ImageReader(imagem), 0, 0, width=largura_pt, height=altura_pt)
            pdf_saida.showPage()
        if total_ocorrencias == 0:
            return {"erro": "Nenhuma ocorrência foi detectada por OCR; nenhum arquivo foi gerado."}
        pdf_saida.save()
        buffer_pdf.seek(0)
        out.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(buffer_pdf.getvalue())
        validado = PdfReader(str(temp), strict=True)
        if len(validado.pages) != len(doc):
            temp.unlink(missing_ok=True)
            return {"erro": "Validação de páginas falhou; original preservado."}
        # Saída rasterizada: não deve conter texto selecionável nem objetos vetoriais originais.
        if any((pagina.extract_text() or "").strip() for pagina in validado.pages):
            temp.unlink(missing_ok=True)
            return {"erro": "A saída ainda contém texto selecionável; original preservado."}
        temp.replace(out)
        return {
            "mensagem": "PDF rasterizado e termos detectados cobertos com tarjas pretas.",
            "destino": str(out), "ocorrencias_detectadas": total_ocorrencias,
            "paginas_afetadas": sorted(paginas_com_ocorrencia),
            "paginas": len(validado.pages), "texto_selecionavel_removido": True,
            "observacao": "A redação remove o conteúdo original ao rasterizar todas as páginas. OCR pode falhar em textos pouco legíveis, manuscritos ou idiomas ausentes; revise visualmente cada página antes de compartilhar."
        }
    except Exception as exc:
        temp.unlink(missing_ok=True)
        return {"erro": f"Falha na censura OCR: {exc}. O arquivo original foi preservado."}


@ferramenta(
    "pdf_pdfa",
    "Converte PDF para PDF/A-1b, PDF/A-2b ou PDF/A-3b usando Ghostscript e perfil ICC fornecido.",
    {"arquivo": texto("PDF de origem"), "perfil_icc": texto("Caminho de perfil ICC RGB válido"),
     "versao": texto("1|2|3"), "destino": texto("PDF/A de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "perfil_icc"],
)
def pdf_pdfa(ctx, arquivo: str, perfil_icc: str, versao: str = "2", destino: str = ""):
    origem, perfil = _path(ctx, arquivo), _path(ctx, perfil_icc)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    if not perfil.is_file() or perfil.suffix.lower() not in (".icc", ".icm"):
        return {"erro": "Informe um perfil ICC RGB válido (.icc/.icm)."}
    versao = str(versao or "2")
    if versao not in ("1", "2", "3"):
        return {"erro": "Ghostscript suporta PDF/A-1b, PDF/A-2b ou PDF/A-3b (versao 1, 2 ou 3)."}
    gs = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    if not gs:
        return {"erro": "Ghostscript não encontrado. Instale-o no sistema para converter PDF/A."}
    out = _path(ctx, destino or f"{origem.stem}_pdfa{versao}.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_name(out.name + ".tmp")
    definicao = out.with_name(f".{out.stem}_pdfa_def.ps")
    caminho_icc = str(perfil).replace("\\", "/").replace("(", "\\(").replace(")", "\\)")
    ps = f"""/ICCProfile ({caminho_icc}) def
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} << /N 3 >> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} << /Type /OutputIntent /S /GTS_PDFA1
  /DestOutputProfile {{icc_PDFA}} /OutputConditionIdentifier (sRGB) >> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent_PDFA}} ] >> /PUT pdfmark
"""
    try:
        definicao.write_text(ps, encoding="ascii")
        comando = [
            gs, f"-dPDFA={versao}", "-dBATCH", "-dNOPAUSE",
            "-sColorConversionStrategy=RGB", "-sProcessColorModel=DeviceRGB",
            "-sDEVICE=pdfwrite", "-dPDFACompatibilityPolicy=2",
            f"--permit-file-read={perfil}", f"-sOutputFile={temp}",
            str(definicao), str(origem),
        ]
        proc = subprocess.run(comando, check=True, timeout=300, capture_output=True, text=True)
        from pypdf import PdfReader
        leitor = PdfReader(str(temp), strict=True)
        if not leitor.pages or len(leitor.pages) < 1:
            temp.unlink(missing_ok=True)
            return {"erro": "Ghostscript não gerou um PDF válido."}
        temp.replace(out)
        verapdf = shutil.which("verapdf")
        validacao = "não executada; instale veraPDF para validação formal"
        if verapdf:
            resultado = subprocess.run([verapdf, "--format", "text", str(out)],
                                       capture_output=True, text=True, timeout=180)
            saida = (resultado.stdout or "") + (resultado.stderr or "")
            validacao = "aprovado pelo veraPDF" if resultado.returncode == 0 and "PASS" in saida.upper() else "veraPDF não confirmou conformidade"
        return {
            "mensagem": f"Conversão para PDF/A-{versao}b concluída pelo Ghostscript.",
            "destino": str(out), "paginas": len(leitor.pages),
            "validacao_formal": validacao,
            "avisos_ghostscript": (proc.stderr or "")[:3000],
        }
    except subprocess.CalledProcessError as exc:
        temp.unlink(missing_ok=True)
        return {"erro": f"Ghostscript recusou a conversão para PDF/A: {(exc.stderr or str(exc))[-3000:]}. Original preservado."}
    except Exception as exc:
        temp.unlink(missing_ok=True)
        return {"erro": f"Falha na conversão PDF/A: {exc}. Original preservado."}
    finally:
        definicao.unlink(missing_ok=True)


@ferramenta(
    "pdf_para_word_ocr",
    "Converte PDF para DOCX usando texto nativo e OCR nas páginas digitalizadas.",
    {"arquivo": texto("PDF de origem"), "idioma": texto("Idioma Tesseract (por, eng...)"),
     "destino": texto("DOCX de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_para_word_ocr(ctx, arquivo: str, idioma: str = "por", destino: str = ""):
    try:
        from docx import Document
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError:
        return {"erro": "PDF para Word com OCR requer python-docx, pypdfium2, pytesseract e Tesseract instalado."}
    from pypdf import PdfReader
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    try:
        reader = PdfReader(str(origem), strict=False)
        doc_pdfium = pdfium.PdfDocument(str(origem))
        docx = Document()
        paginas_ocr = []
        for i, page in enumerate(reader.pages):
            conteudo = (page.extract_text() or "").strip()
            if not conteudo:
                imagem = doc_pdfium[i].render(scale=2).to_pil()
                conteudo = pytesseract.image_to_string(imagem, lang=idioma or "por").strip()
                paginas_ocr.append(i+1)
            if i:
                docx.add_page_break()
            docx.add_heading(f"Página {i+1}", level=1)
            docx.add_paragraph(conteudo or "[Nenhum texto reconhecido nesta página]")
        out = _path(ctx, destino or f"{origem.stem}_editavel.docx")
        if out.suffix.lower() != ".docx":
            out = out.with_suffix(".docx")
        out.parent.mkdir(parents=True, exist_ok=True)
        docx.save(out)
        return {"mensagem": "DOCX gerado com texto nativo e OCR quando necessário.",
                "destino": str(out), "paginas": len(reader.pages),
                "paginas_processadas_por_ocr": paginas_ocr,
                "observacao": "O texto fica editável, mas a diagramação original não é preservada."}
    except Exception as exc:
        return {"erro": f"Falha ao converter PDF para Word: {exc}"}


@ferramenta(
    "pdf_extrair_imagens",
    "Extrai imagens incorporadas em um PDF e gera um ZIP com os arquivos originais encontrados.",
    {"arquivo": texto("PDF de origem"), "destino": texto("Pasta ou ZIP de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_extrair_imagens(ctx, arquivo: str, destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, _ = deps
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    out = _path(ctx, destino or f"{origem.stem}_imagens.zip")
    pasta = out.with_suffix("")
    try:
        reader = PdfReader(str(origem), strict=False)
        pasta.mkdir(parents=True, exist_ok=True)
        arquivos = []
        for num_pagina, page in enumerate(reader.pages, 1):
            for indice, imagem in enumerate(page.images, 1):
                nome = Path(imagem.name).name
                extensao = Path(nome).suffix or ".bin"
                alvo = pasta / f"pagina_{num_pagina:04d}_imagem_{indice:03d}{extensao}"
                alvo.write_bytes(imagem.data)
                arquivos.append(alvo)
        if not arquivos:
            return {"erro": "Nenhuma imagem incorporada foi encontrada no PDF."}
        if out.suffix.lower() != ".zip":
            out = out.with_suffix(".zip")
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
            for item in arquivos:
                pacote.write(item, item.name)
        return {"mensagem": f"Extraí {len(arquivos)} imagem(ns).",
                "zip": str(out), "pasta": str(pasta), "arquivos": [x.name for x in arquivos]}
    except Exception as exc:
        return {"erro": f"Falha ao extrair imagens: {exc}"}


@ferramenta(
    "pdf_copiar",
    "Cria uma cópia independente de um PDF, preservando o original.",
    {"arquivo": texto("PDF de origem"), "destino": texto("Caminho da cópia")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo", "destino"],
)
def pdf_copiar(ctx, arquivo: str, destino: str):
    origem, out = _path(ctx, arquivo), _path(ctx, destino)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    if origem.resolve() == out.resolve():
        return {"erro": "O destino deve ser diferente do arquivo original."}
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, out)
        return {"mensagem": "Cópia criada.", "destino": str(out),
                "tamanho_bytes": out.stat().st_size}
    except Exception as exc:
        return {"erro": f"Falha ao copiar PDF: {exc}"}


@ferramenta(
    "pdf_criar_formulario",
    "Cria PDF preenchível com campos de texto, caixas de seleção e listas de opções (AcroForm).",
    {"campos": texto("JSON: lista de campos com nome, tipo, x, y, largura, altura, pagina e opções"),
     "paginas": numero("Quantidade de páginas em branco"), "destino": texto("PDF preenchível")},
    grupo="pdf", risco=MODERADO, obrigatorios=["campos"],
)
def pdf_criar_formulario(ctx, campos: str, paginas: int = 1, destino: str = ""):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        return {"erro": 'Criação de formulários requer reportlab. Instale: pip install "optimus-assistente[pdf]"'}
    try:
        definicoes = json.loads(campos)
        if not isinstance(definicoes, list) or not definicoes:
            return {"erro": "campos deve ser uma lista JSON não vazia."}
        total_paginas = max(1, min(int(paginas or 1), 100))
        nomes, validados = set(), []
        for campo in definicoes:
            if not isinstance(campo, dict):
                return {"erro": "Cada campo deve ser um objeto JSON."}
            nome = str(campo.get("nome", "")).strip()
            tipo = str(campo.get("tipo", "texto")).lower()
            if not nome or nome in nomes or tipo not in ("texto", "checkbox", "lista"):
                return {"erro": "Campos precisam de nomes únicos e tipo texto, checkbox ou lista."}
            nomes.add(nome)
            pagina = int(campo.get("pagina", 1))
            if pagina < 1 or pagina > total_paginas:
                return {"erro": f"Página inválida no campo {nome}."}
            validados.append({**campo, "nome": nome, "tipo": tipo, "pagina": pagina})
        out = _path(ctx, destino or "formulario_preenchivel.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(out), pagesize=A4)
        form = c.acroForm
        for numero_pagina in range(1, total_paginas+1):
            for campo in (x for x in validados if x["pagina"] == numero_pagina):
                x, y = float(campo.get("x", 72)), float(campo.get("y", 700))
                w, h = max(12, float(campo.get("largura", 220))), max(12, float(campo.get("altura", 24)))
                rotulo = str(campo.get("rotulo", campo["nome"]))[:120]
                c.setFont("Helvetica", 9)
                c.drawString(max(0, x), min(820, y+h+5), rotulo)
                if campo["tipo"] == "texto":
                    form.textfield(name=campo["nome"], x=x, y=y, width=w, height=h,
                                   borderStyle="inset", forceBorder=True,
                                   value=str(campo.get("valor", ""))[:500])
                elif campo["tipo"] == "checkbox":
                    form.checkbox(name=campo["nome"], x=x, y=y, size=min(w, h, 24),
                                  checked=bool(campo.get("valor", False)), buttonStyle="check",
                                  borderWidth=1, forceBorder=True)
                else:
                    opcoes = campo.get("opcoes", [])
                    if not isinstance(opcoes, list) or not opcoes:
                        return {"erro": f"O campo lista {campo['nome']} precisa de opcoes."}
                    form.choice(name=campo["nome"], options=[str(v) for v in opcoes],
                                x=x, y=y, width=w, height=h,
                                value=str(campo.get("valor", opcoes[0])),
                                borderStyle="solid", forceBorder=True)
            c.showPage()
        c.save()
        from pypdf import PdfReader
        leitor = PdfReader(str(out), strict=True)
        campos_saida = leitor.get_fields() or {}
        if len(campos_saida) != len(validados):
            out.unlink(missing_ok=True)
            return {"erro": "A validação não encontrou todos os campos criados."}
        return {"mensagem": "Formulário PDF preenchível criado e validado.",
                "destino": str(out), "paginas": len(leitor.pages),
                "campos": list(campos_saida)}
    except Exception as exc:
        return {"erro": f"Falha ao criar formulário PDF: {exc}"}


@ferramenta(
    "pdf_workflow",
    "Salva, lista e executa fluxos reutilizáveis de ferramentas PDF em sequência.",
    {"acao": texto("salvar|listar|executar"), "nome": texto("Nome do fluxo"),
     "etapas": texto("JSON: lista de objetos {ferramenta, argumentos}")},
    grupo="pdf", risco=MODERADO, obrigatorios=["acao"],
)
def pdf_workflow(ctx, acao: str, nome: str = "", etapas: str = ""):
    from optimus.tools.base import registradas
    pasta = _path(ctx, ".optimus/pdf-workflows")
    pasta.mkdir(parents=True, exist_ok=True)
    acao = (acao or "").lower()
    if acao == "listar":
        return {"fluxos": sorted(x.stem for x in pasta.glob("*.json"))}
    caminho_nome = re.sub(r"[^a-zA-Z0-9_-]", "_", nome or "").strip("_")
    if not caminho_nome:
        return {"erro": "Informe um nome de fluxo válido."}
    arquivo_fluxo = pasta / f"{caminho_nome[:80]}.json"
    if acao == "salvar":
        try:
            lista = json.loads(etapas)
            if not isinstance(lista, list) or not lista:
                return {"erro": "etapas deve ser uma lista JSON não vazia."}
            registro = registradas()
            for etapa in lista:
                if not isinstance(etapa, dict) or etapa.get("ferramenta") not in registro:
                    return {"erro": f"Ferramenta desconhecida na etapa: {etapa}"}
                if registro[etapa["ferramenta"]].grupo != "pdf" or etapa["ferramenta"] == "pdf_workflow":
                    return {"erro": "Fluxos só podem executar ferramentas PDF, sem recursão."}
                if not isinstance(etapa.get("argumentos", {}), dict):
                    return {"erro": "argumentos de cada etapa deve ser um objeto JSON."}
            arquivo_fluxo.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"mensagem": "Fluxo salvo.", "nome": caminho_nome, "etapas": len(lista)}
        except Exception as exc:
            return {"erro": f"Não foi possível salvar o fluxo: {exc}"}
    if acao == "executar":
        try:
            lista = json.loads(etapas) if etapas.strip() else json.loads(arquivo_fluxo.read_text(encoding="utf-8"))
            if not isinstance(lista, list) or not lista:
                return {"erro": "O fluxo não contém etapas."}
            registro = registradas()
            resultados = []
            for indice, etapa in enumerate(lista, 1):
                nome_ferramenta = etapa.get("ferramenta")
                ferramenta_pdf = registro.get(nome_ferramenta)
                if not ferramenta_pdf or ferramenta_pdf.grupo != "pdf" or nome_ferramenta == "pdf_workflow":
                    return {"erro": f"Etapa {indice}: ferramenta PDF não permitida.",
                            "etapas_concluidas": resultados}
                try:
                    resultado = ferramenta_pdf.funcao(ctx, **etapa.get("argumentos", {}))
                except Exception as exc:
                    resultado = {"erro": f"{type(exc).__name__}: {exc}"}
                if isinstance(resultado, str):
                    try:
                        resultado = json.loads(resultado)
                    except ValueError:
                        resultado = {"resultado": resultado}
                resultados.append({"etapa": indice, "ferramenta": nome_ferramenta, "resultado": resultado})
                if isinstance(resultado, dict) and resultado.get("erro"):
                    return {"erro": f"Fluxo interrompido na etapa {indice}.",
                            "etapas_concluidas": resultados}
            return {"mensagem": "Fluxo concluído.", "etapas": resultados}
        except FileNotFoundError:
            return {"erro": f"Fluxo não encontrado: {caminho_nome}"}
        except Exception as exc:
            return {"erro": f"Falha ao executar fluxo: {exc}"}
    return {"erro": "Ação deve ser salvar, listar ou executar."}


@ferramenta(
    "pdf_documento_para_pdf",
    "Converte arquivos Word, Excel, PowerPoint, LibreOffice, RTF, TXT e CSV para PDF usando LibreOffice instalado.",
    {"arquivo": texto("Documento de origem"), "destino": texto("PDF de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_documento_para_pdf(ctx, arquivo: str, destino: str = ""):
    origem = _path(ctx, arquivo)
    extensoes = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                 ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv"}
    if not origem.is_file() or origem.suffix.lower() not in extensoes:
        return {"erro": "Selecione um documento Word, Excel, PowerPoint, LibreOffice, RTF, TXT ou CSV válido."}
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return {"erro": "Conversão Office para PDF requer LibreOffice instalado no computador (Windows/Linux)."}
    saida = _path(ctx, destino or f"{origem.stem}.pdf")
    saida.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="optimus-pdf-office-") as temporario:
            perfil = Path(temporario) / "perfil"
            pasta_saida = Path(temporario) / "saida"
            pasta_saida.mkdir()
            comando = [soffice, "--headless", "--nologo", "--nodefault", "--nolockcheck",
                       f"-env:UserInstallation={perfil.as_uri()}", "--convert-to", "pdf",
                       "--outdir", str(pasta_saida), str(origem)]
            processo = subprocess.run(comando, capture_output=True, text=True, timeout=180, check=False)
            gerado = pasta_saida / f"{origem.stem}.pdf"
            if processo.returncode != 0 or not gerado.is_file():
                detalhe = (processo.stderr or processo.stdout or "LibreOffice não gerou o PDF.").strip()
                return {"erro": f"Falha na conversão: {detalhe[:800]}"}
            shutil.copy2(gerado, saida)
        from pypdf import PdfReader
        paginas = len(PdfReader(str(saida)).pages)
        return {"mensagem": f"Documento convertido para PDF com {paginas} página(s).",
                "destino": str(saida), "paginas": paginas, "tamanho_bytes": saida.stat().st_size}
    except subprocess.TimeoutExpired:
        return {"erro": "A conversão excedeu 3 minutos e foi interrompida."}
    except Exception as exc:
        return {"erro": f"Não consegui converter o documento: {exc}"}


@ferramenta(
    "pdf_unir_documentos",
    "Une PDFs, imagens e documentos Office em um único PDF, preservando a ordem informada.",
    {"arquivos": texto("Caminhos dos arquivos separados por vírgula ou ponto-e-vírgula"),
     "destino": texto("PDF final")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivos"],
)
def pdf_unir_documentos(ctx, arquivos: str, destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, PdfWriter = deps
    entradas = [x.strip().strip('"') for x in re.split(r"[,;]+", arquivos or "") if x.strip()]
    if len(entradas) < 2:
        return {"erro": "Selecione pelo menos dois arquivos para unir."}
    saida = _path(ctx, destino or "documentos_unidos.pdf")
    saida.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="optimus-pdf-merge-") as temporario:
            escritor = PdfWriter()
            for indice, item in enumerate(entradas):
                origem = _path(ctx, item)
                if not origem.is_file():
                    return {"erro": f"Arquivo não encontrado: {origem.name}"}
                extensao = origem.suffix.lower()
                convertido = origem
                if extensao != ".pdf":
                    convertido = Path(temporario) / f"parte_{indice + 1}.pdf"
                    if extensao in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}:
                        resultado = pdf_imagens_para_pdf(ctx, str(origem), str(convertido))
                    else:
                        resultado = pdf_documento_para_pdf(ctx, str(origem), str(convertido))
                    if resultado.get("erro"):
                        return resultado
                leitor = PdfReader(str(convertido), strict=False)
                if leitor.is_encrypted:
                    return {"erro": f"O arquivo {origem.name} está protegido. Desbloqueie-o antes de unir."}
                for pagina in leitor.pages:
                    escritor.add_page(pagina)
            with open(saida, "wb") as destino_pdf:
                escritor.write(destino_pdf)
        paginas = len(PdfReader(str(saida)).pages)
        return {"mensagem": f"{len(entradas)} arquivos unidos em um PDF com {paginas} página(s).",
                "destino": str(saida), "paginas": paginas, "tamanho_bytes": saida.stat().st_size}
    except Exception as exc:
        return {"erro": f"Falha ao unir documentos: {exc}"}


@ferramenta(
    "pdf_dividir_pares_impares",
    "Divide um PDF em dois arquivos: páginas ímpares (1, 3, 5...) e pares (2, 4, 6...). "
    "Preserva o conteúdo vetorial e o texto selecionável.",
    {"arquivo": texto("PDF de origem"), "destino_impares": texto("PDF de páginas ímpares"),
     "destino_pares": texto("PDF de páginas pares")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_dividir_pares_impares(ctx, arquivo: str, destino_impares: str = "",
                              destino_pares: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, PdfWriter = deps
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    try:
        leitor = PdfReader(str(origem), strict=False)
        if leitor.is_encrypted:
            return {"erro": "O PDF está protegido. Desbloqueie-o antes de dividir."}
        impares, pares = PdfWriter(), PdfWriter()
        for indice, pagina in enumerate(leitor.pages):
            (impares if indice % 2 == 0 else pares).add_page(pagina)
        base = origem.with_suffix("")
        saida_i = _path(ctx, destino_impares or f"{base.name}_impares.pdf")
        saida_p = _path(ctx, destino_pares or f"{base.name}_pares.pdf")
        saida_i.parent.mkdir(parents=True, exist_ok=True)
        saida_p.parent.mkdir(parents=True, exist_ok=True)
        if len(impares.pages):
            with saida_i.open("wb") as f:
                impares.write(f)
        if len(pares.pages):
            with saida_p.open("wb") as f:
                pares.write(f)
        return {"mensagem": "PDF separado em páginas ímpares e pares.",
                "impares": str(saida_i) if len(impares.pages) else "",
                "paginas_impares": len(impares.pages),
                "pares": str(saida_p) if len(pares.pages) else "",
                "paginas_pares": len(pares.pages)}
    except Exception as exc:
        return {"erro": f"Falha ao separar páginas pares e ímpares: {exc}"}


def _compor_folha(escritor, paginas, largura: float, altura: float,
                  colunas: int, linhas: int) -> None:
    from copy import copy
    from pypdf import Transformation

    celula_w, celula_h = largura / colunas, altura / linhas
    for indice, pagina in enumerate(paginas):
        if pagina is None:
            continue
        coluna, linha = indice % colunas, indice // colunas
        caixa = pagina.mediabox
        pw, ph = float(caixa.width), float(caixa.height)
        escala = min(celula_w / pw, celula_h / ph)
        x = coluna * celula_w + (celula_w - pw * escala) / 2
        y = altura - (linha + 1) * celula_h + (celula_h - ph * escala) / 2
        escritor.pages[-1].merge_transformed_page(
            copy(pagina), Transformation().scale(escala).translate(x, y)
        )


@ferramenta(
    "pdf_paginas_por_folha",
    "Coloca 2, 4, 6 ou 9 páginas de origem em cada folha, preservando texto e vetores.",
    {"arquivo": texto("PDF de origem"), "por_folha": numero("Quantidade: 2, 4, 6 ou 9"),
     "destino": texto("PDF de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_paginas_por_folha(ctx, arquivo: str, por_folha: int = 2, destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, PdfWriter = deps
    quantidade = int(por_folha or 2)
    grades = {2: (2, 1), 4: (2, 2), 6: (3, 2), 9: (3, 3)}
    if quantidade not in grades:
        return {"erro": "por_folha deve ser 2, 4, 6 ou 9."}
    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    saida = _path(ctx, destino or f"{origem.stem}_{quantidade}porfolha.pdf")
    try:
        leitor = PdfReader(str(origem), strict=False)
        if leitor.is_encrypted:
            return {"erro": "O PDF está protegido. Desbloqueie-o antes de organizar."}
        colunas, linhas = grades[quantidade]
        primeira = leitor.pages[0]
        largura, altura = float(primeira.mediabox.width), float(primeira.mediabox.height)
        escritor = PdfWriter()
        for inicio in range(0, len(leitor.pages), quantidade):
            grupo = leitor.pages[inicio:inicio + quantidade]
            escritor.add_blank_page(width=largura, height=altura)
            _compor_folha(escritor, grupo, largura, altura, colunas, linhas)
        saida.parent.mkdir(parents=True, exist_ok=True)
        with saida.open("wb") as f:
            escritor.write(f)
        return {"mensagem": f"Organizei {len(leitor.pages)} páginas em {len(escritor.pages)} folha(s).",
                "destino": str(saida), "paginas_origem": len(leitor.pages),
                "folhas_saida": len(escritor.pages), "por_folha": quantidade}
    except Exception as exc:
        return {"erro": f"Falha ao montar páginas por folha: {exc}"}


@ferramenta(
    "pdf_imprimir_livreto",
    "Reorganiza as páginas em ordem de livreto (imposição frente e verso), duas páginas por lado. "
    "A impressão deve ser feita em frente e verso com virada pela borda curta.",
    {"arquivo": texto("PDF de origem"), "destino": texto("PDF de saída")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivo"],
)
def pdf_imprimir_livreto(ctx, arquivo: str, destino: str = ""):
    deps = _pypdf()
    if not deps:
        return {"erro": 'Instale: pip install "optimus-assistente[pdf]"'}
    PdfReader, PdfWriter = deps
    from pypdf import Transformation
    from copy import copy

    origem = _path(ctx, arquivo)
    if not origem.is_file():
        return {"erro": f"PDF não encontrado: {origem}"}
    saida = _path(ctx, destino or f"{origem.stem}_livreto.pdf")
    try:
        leitor = PdfReader(str(origem), strict=False)
        if leitor.is_encrypted:
            return {"erro": "O PDF está protegido. Desbloqueie-o antes de montar o livreto."}
        paginas = list(leitor.pages)
        total = len(paginas)
        preenchido = ((total + 3) // 4) * 4
        paginas.extend([None] * (preenchido - total))
        primeira = next(p for p in paginas if p is not None)
        largura, altura = float(primeira.mediabox.width), float(primeira.mediabox.height)
        escritor = PdfWriter()
        for folha in range(preenchido // 4):
            pares = [(preenchido - 1 - 2 * folha, 2 * folha),
                     (2 * folha + 1, preenchido - 2 - 2 * folha)]
            for esquerda, direita in pares:
                escritor.add_blank_page(width=largura * 2, height=altura)
                alvo = escritor.pages[-1]
                for indice, x in ((esquerda, 0), (direita, largura)):
                    pagina = paginas[indice]
                    if pagina is None:
                        continue
                    pw, ph = float(pagina.mediabox.width), float(pagina.mediabox.height)
                    escala = min(largura / pw, altura / ph)
                    tx = x + (largura - pw * escala) / 2
                    ty = (altura - ph * escala) / 2
                    alvo.merge_transformed_page(copy(pagina),
                        Transformation().scale(escala).translate(tx, ty))
        saida.parent.mkdir(parents=True, exist_ok=True)
        with saida.open("wb") as f:
            escritor.write(f)
        return {"mensagem": f"Livreto criado: {total} páginas de conteúdo em {len(escritor.pages)} lados.",
                "destino": str(saida), "paginas_origem": total,
                "lados_saida": len(escritor.pages), "impressao_frente_verso": True}
    except Exception as exc:
        return {"erro": f"Falha ao montar livreto: {exc}"}
