from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from optimus.config import Config
from optimus.tools import pdf, pdf_suite
from optimus.tools.base import Contexto


def _ctx(tmp_path):
    return Contexto(config=Config(), pasta_trabalho=tmp_path)


def _criar_pdf(path: Path, paginas: list[str]):
    documento = canvas.Canvas(str(path))
    for texto in paginas:
        documento.drawString(72, 720, texto)
        documento.showPage()
    documento.save()


def test_pdf_organizar_preserva_ordem_exatamente(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "ordem.pdf"
    _criar_pdf(origem, ["PAGINA UM", "PAGINA DOIS", "PAGINA TRES"])

    resultado = pdf.pdf_organizar(_ctx(tmp_path), str(origem), "3,1,2", str(destino))

    assert "erro" not in resultado
    textos = [p.extract_text().strip() for p in PdfReader(str(destino)).pages]
    assert textos == ["PAGINA TRES", "PAGINA UM", "PAGINA DOIS"]


def test_pdf_marca_aplica_texto_visivel(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "marca.pdf"
    _criar_pdf(origem, ["CONTEUDO ORIGINAL"])

    resultado = pdf.pdf_marca(_ctx(tmp_path), str(origem), "CONFIDENCIAL", str(destino))

    assert resultado.get("visual") is True
    texto = PdfReader(str(destino)).pages[0].extract_text()
    assert "CONTEUDO ORIGINAL" in texto
    assert "CONFIDENCIAL" in texto


def test_pdf_numeros_insere_numeros_visiveis(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "numerado.pdf"
    _criar_pdf(origem, ["PAGINA UM", "PAGINA DOIS"])

    resultado = pdf.pdf_numeros(_ctx(tmp_path), str(origem), str(destino))

    assert resultado["paginas_numeradas"] == 2
    paginas = [p.extract_text() for p in PdfReader(str(destino)).pages]
    assert all(any(linha.strip() == str(n) for linha in texto.splitlines()) for n, texto in enumerate(paginas, 1))


def test_pdf_localizar_termos_nao_altera_original_e_censurar_recusa(tmp_path):
    origem = tmp_path / "original.pdf"
    _criar_pdf(origem, ["CPF 123456", "SEM DADO"])
    tamanho = origem.stat().st_size

    localizados = pdf.pdf_localizar_termos(_ctx(tmp_path), str(origem), "123456")
    censura = pdf.pdf_censurar(_ctx(tmp_path), str(origem), "123456")

    assert localizados["total_ocorrencias"] == 1
    assert localizados["ocorrencias"][0]["pagina"] == 1
    assert "não está implementada" in censura["erro"]
    assert origem.stat().st_size == tamanho


def test_pdf_converter_escapa_html_e_gera_docx_real(tmp_path):
    origem = tmp_path / "origem.pdf"
    html_out = tmp_path / "saida.html"
    docx_out = tmp_path / "saida.docx"
    _criar_pdf(origem, ["<script>alert(1)</script>"])

    html_result = pdf.pdf_converter(_ctx(tmp_path), str(origem), "html", str(html_out))
    docx_result = pdf.pdf_converter(_ctx(tmp_path), str(origem), "docx", str(docx_out))

    assert "erro" not in html_result and "&lt;script&gt;" in html_out.read_text(encoding="utf-8")
    assert "erro" not in docx_result and docx_out.is_file()
    from docx import Document
    assert any("<script>" in p.text for p in Document(str(docx_out)).paragraphs)


def test_pdf_imagens_para_pdf_cria_uma_pagina_por_imagem(tmp_path):
    from PIL import Image

    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (80, 120), "white").save(a)
    Image.new("RGB", (120, 80), "black").save(b)
    destino = tmp_path / "fotos.pdf"

    resultado = pdf_suite.pdf_imagens_para_pdf(
        _ctx(tmp_path), f"{a};{b}", str(destino), "auto", 18
    )

    assert "erro" not in resultado
    assert resultado["paginas"] == 2
    assert len(PdfReader(str(destino)).pages) == 2


def test_pdf_para_markdown_preserva_paginas(tmp_path):
    origem = tmp_path / "texto.pdf"
    destino = tmp_path / "texto.md"
    _criar_pdf(origem, ["PRIMEIRA PAGINA", "SEGUNDA PAGINA"])

    resultado = pdf.pdf_suite.pdf_para_markdown(_ctx(tmp_path), str(origem), str(destino))

    assert "erro" not in resultado
    conteudo = destino.read_text(encoding="utf-8")
    assert "## Página 1" in conteudo and "PRIMEIRA PAGINA" in conteudo
    assert "## Página 2" in conteudo and "SEGUNDA PAGINA" in conteudo


def test_pdf_cortar_aplica_cropbox_sem_perder_paginas(tmp_path):
    from pypdf import PdfReader

    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "cortado.pdf"
    _criar_pdf(origem, ["CONTEUDO"])
    antes = PdfReader(str(origem)).pages[0].cropbox
    resultado = pdf.pdf_suite.pdf_cortar(
        _ctx(tmp_path), str(origem), 10, 12, 14, 16, "", str(destino)
    )

    assert "erro" not in resultado
    depois = PdfReader(str(destino)).pages[0].cropbox
    assert float(depois.width) == float(antes.width) - 24
    assert float(depois.height) == float(antes.height) - 28


def test_pdf_metadados_remove_campos_de_metadados(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "limpo.pdf"
    _criar_pdf(origem, ["DOCUMENTO"])
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(str(origem))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({"/Author": "Autor confidencial", "/Title": "Titulo"})
    with origem.open("wb") as arquivo:
        writer.write(arquivo)

    resultado = pdf.pdf_suite.pdf_metadados(
        _ctx(tmp_path), str(origem), "remover", "", str(destino)
    )

    assert "erro" not in resultado
    metadata = PdfReader(str(destino)).metadata
    assert not metadata or not metadata.get("/Author")


def test_pdf_reparar_reconstroi_e_valida_pdf_legivel(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "reparado.pdf"
    _criar_pdf(origem, ["PAGINA UM", "PAGINA DOIS"])

    resultado = pdf.pdf_suite.pdf_reparar(_ctx(tmp_path), str(origem), str(destino))

    assert "erro" not in resultado
    leitor = PdfReader(str(destino), strict=True)
    assert len(leitor.pages) == 2
    assert "PAGINA UM" in leitor.pages[0].extract_text()
