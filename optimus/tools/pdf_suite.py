"""Ferramentas adicionais de PDF para paridade local com suítes comerciais.

Todas as operações são executadas localmente. Dependências opcionais são verificadas
no momento do uso para que a instalação básica do Optimus continue leve.
"""
from __future__ import annotations

import json
import shutil
import subprocess
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
     "margem": numero("Margem em pontos (padrão 24)")},
    grupo="pdf", risco=MODERADO, obrigatorios=["arquivos"],
)
def pdf_imagens_para_pdf(ctx, arquivos: str, destino: str = "",
                         orientacao: str = "auto", margem: int = 24):
    try:
        from PIL import Image
        from reportlab.lib.pagesizes import A4, landscape, portrait
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except ImportError:
        return {"erro": 'Conversão de imagens requer Pillow e reportlab. Instale: pip install "optimus-assistente[pdf]"'}
    import re
    lista = [x.strip().strip('"') for x in re.split(r"[,;]+", arquivos) if x.strip()]
    if not lista:
        return {"erro": "Informe ao menos uma imagem."}
    imagens = []
    for nome in lista:
        p = _path(ctx, nome)
        if not p.is_file():
            return {"erro": f"Imagem não encontrada: {p}"}
        try:
            with Image.open(p) as img:
                imagens.append(img.convert("RGB").copy())
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
            modo = (orientacao or "auto").lower()
            if modo == "paisagem" or (modo == "auto" and img.width > img.height):
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
            "paginas": len(imagens), "tamanho_bytes": out.stat().st_size}


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
        return {"erro": 'Instale: pip install "optimus-assistente[documentos]"'}
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
        return {"erro": 'Instale: pip install "optimus-assistente[documentos]"'}
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
        return {"erro": 'Instale: pip install "optimus-assistente[documentos]"'}
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
        return {"erro": 'Instale: pip install "optimus-assistente[documentos]"'}
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
        return {"erro": 'Instale: pip install "optimus-assistente[documentos]"'}
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
        with pdfplumber.open(str(origem)) as pdf:
            for numero_pagina, page in enumerate(pdf.pages, 1):
                achadas = page.extract_tables() or []
                for indice, tabela in enumerate(achadas, 1):
                    tabelas += 1
                    sheet = workbook.create_sheet(f"P{numero_pagina}_T{indice}"[:31])
                    for linha in tabela:
                        sheet.append([celula or "" for celula in linha])
                texto_pagina = page.extract_text() or ""
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
                "destino": str(out), "tabelas_detectadas": tabelas,
                "observacao": "Tabelas detectadas são aproximadas; confira células mescladas e layout."}
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
        return {"erro": 'Instale: pip install "optimus-assistente[documentos]"'}
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
            page.merge_page(PdfReader(buffer).pages[0])
            writer.add_page(page)
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
