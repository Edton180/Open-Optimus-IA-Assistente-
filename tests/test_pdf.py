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


def test_pdf_localizar_termos_nao_altera_original(tmp_path):
    origem = tmp_path / "original.pdf"
    _criar_pdf(origem, ["CPF 123456", "SEM DADO"])
    tamanho = origem.stat().st_size

    localizados = pdf.pdf_localizar_termos(_ctx(tmp_path), str(origem), "123456")

    assert localizados["total_ocorrencias"] == 1
    assert localizados["ocorrencias"][0]["pagina"] == 1
    assert origem.stat().st_size == tamanho


def test_pdf_censurar_rasteriza_remove_texto_original_e_valida_ocr(tmp_path, monkeypatch):
    import sys
    import types
    from PIL import Image
    from pypdf import PdfReader

    origem = tmp_path / "original.pdf"
    destino = tmp_path / "censurado.pdf"
    _criar_pdf(origem, ["CPF 12345678900"])

    class PaginaFalsa:
        def render(self, scale):
            return types.SimpleNamespace(to_pil=lambda: Image.new("RGB", (300, 400), "white"))

    class DocumentoFalso:
        def __init__(self, path):
            self.paginas = [PaginaFalsa()]
        def __len__(self):
            return len(self.paginas)
        def __getitem__(self, index):
            return self.paginas[index]

    chamadas = {"n": 0}
    def ocr_data(imagem, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return {"text": ["12345678900"], "left": [50], "top": [60],
                    "width": [130], "height": [24]}
        return {"text": [""], "left": [0], "top": [0], "width": [0], "height": [0]}

    fake_tesseract = types.SimpleNamespace(
        Output=types.SimpleNamespace(DICT="dict"), image_to_data=ocr_data
    )
    fake_pdfium = types.SimpleNamespace(PdfDocument=DocumentoFalso)
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tesseract)
    monkeypatch.setitem(sys.modules, "pypdfium2", fake_pdfium)

    resultado = pdf.pdf_censurar(_ctx(tmp_path), str(origem), "12345678900",
                                 str(destino), "por", 3)

    assert "erro" not in resultado
    assert resultado["texto_selecionavel_removido"] is True
    assert PdfReader(str(destino)).pages[0].extract_text() in (None, "")
    assert origem.is_file()


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

    resultado = pdf_suite.pdf_para_markdown(_ctx(tmp_path), str(origem), str(destino))

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
    resultado = pdf_suite.pdf_cortar(
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

    resultado = pdf_suite.pdf_metadados(
        _ctx(tmp_path), str(origem), "remover", "", str(destino)
    )

    assert "erro" not in resultado
    metadata = PdfReader(str(destino)).metadata
    assert not metadata or not metadata.get("/Author")


def test_pdf_reparar_reconstroi_e_valida_pdf_legivel(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "reparado.pdf"
    _criar_pdf(origem, ["PAGINA UM", "PAGINA DOIS"])

    resultado = pdf_suite.pdf_reparar(_ctx(tmp_path), str(origem), str(destino))

    assert "erro" not in resultado
    leitor = PdfReader(str(destino), strict=True)
    assert len(leitor.pages) == 2
    assert "PAGINA UM" in leitor.pages[0].extract_text()


def test_pdf_editar_insere_texto_real_na_pagina(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "editado.pdf"
    _criar_pdf(origem, ["TEXTO ORIGINAL"])

    resultado = pdf_suite.pdf_editar(
        _ctx(tmp_path), str(origem), "texto", "ANOTACAO", 100, 100, 180, 40, 1, str(destino)
    )

    assert "erro" not in resultado
    texto = PdfReader(str(destino)).pages[0].extract_text()
    assert "TEXTO ORIGINAL" in texto and "ANOTACAO" in texto


def test_pdf_para_excel_cria_planilha_com_texto(tmp_path):
    from openpyxl import load_workbook

    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "saida.xlsx"
    _criar_pdf(origem, ["DADO FINANCEIRO", "VALOR 100"])

    resultado = pdf_suite.pdf_para_excel(_ctx(tmp_path), str(origem), str(destino))

    assert "erro" not in resultado
    planilha = load_workbook(destino, read_only=True)
    valores = [celula for linha in planilha["Conteudo"].iter_rows(values_only=True)
               for celula in linha if celula]
    assert any("DADO FINANCEIRO" in str(valor) for valor in valores)


def test_pdf_para_powerpoint_cria_um_slide_por_pagina(tmp_path):
    from pptx import Presentation

    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "saida.pptx"
    _criar_pdf(origem, ["SLIDE UM", "SLIDE DOIS"])

    resultado = pdf_suite.pdf_para_powerpoint(_ctx(tmp_path), str(origem), str(destino), 1)

    assert "erro" not in resultado
    assert len(Presentation(str(destino)).slides) == 2


def test_pdf_comparar_retorna_diff_textual(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _criar_pdf(a, ["VERSAO ANTIGA"])
    _criar_pdf(b, ["VERSAO NOVA"])

    resultado = pdf.pdf_comparar(_ctx(tmp_path), str(a), str(b))

    assert resultado["iguais"] is False
    assert "VERSAO ANTIGA" in resultado["diff"]
    assert "VERSAO NOVA" in resultado["diff"]


def test_pdf_assinar_digital_com_certificado_pkcs12(tmp_path):
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from pypdf import PdfReader

    origem = tmp_path / "contrato.pdf"
    certificado = tmp_path / "teste.p12"
    destino = tmp_path / "assinado.pdf"
    _criar_pdf(origem, ["CONTRATO PARA ASSINAR"])
    senha = "senha-teste"
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Optimus Test")])
    agora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(agora - timedelta(minutes=1))
            .not_valid_after(agora + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(chave, hashes.SHA256()))
    p12 = pkcs12.serialize_key_and_certificates(
        b"Optimus Test", chave, cert, None,
        serialization.BestAvailableEncryption(senha.encode())
    )
    certificado.write_bytes(p12)

    resultado = pdf_suite.pdf_assinar_digital(
        _ctx(tmp_path), str(origem), str(certificado), senha, "AssinaturaTeste", str(destino)
    )

    assert "erro" not in resultado
    campos = PdfReader(str(destino)).get_fields()
    assert any(campo.get("/FT") == "/Sig" and campo.get("/V") for campo in campos.values())


def test_pdf_pdfa_usa_ghostscript_e_nao_finge_validacao_formal(tmp_path, monkeypatch):
    import subprocess

    origem = tmp_path / "origem.pdf"
    perfil = tmp_path / "srgb.icc"
    destino = tmp_path / "arquivo_pdfa.pdf"
    _criar_pdf(origem, ["DOCUMENTO"])
    perfil.write_bytes(b"ICC-TESTE")

    def localizar(nome):
        return "gs" if nome == "gs" else None

    def executar(comando, **kwargs):
        saida = next(arg.split("=", 1)[1] for arg in comando
                     if arg.startswith("-sOutputFile="))
        _criar_pdf(Path(saida), ["PDF-A-GERADO"])
        return subprocess.CompletedProcess(comando, 0, "", "")

    monkeypatch.setattr(pdf_suite.shutil, "which", localizar)
    monkeypatch.setattr(pdf_suite.subprocess, "run", executar)

    resultado = pdf_suite.pdf_pdfa(
        _ctx(tmp_path), str(origem), str(perfil), "2", str(destino)
    )

    assert "erro" not in resultado
    assert resultado["validacao_formal"].startswith("não executada")
    assert len(PdfReader(str(destino)).pages) == 1


def test_pdf_criar_formulario_gera_campos_acroform(tmp_path):
    import json
    from pypdf import PdfReader

    destino = tmp_path / "formulario.pdf"
    campos = [
        {"nome": "nome_completo", "tipo": "texto", "rotulo": "Nome completo", "x": 72, "y": 700},
        {"nome": "aceito", "tipo": "checkbox", "rotulo": "Aceito", "x": 72, "y": 650},
        {"nome": "estado", "tipo": "lista", "rotulo": "Estado", "x": 72, "y": 600,
         "opcoes": ["PA", "SP", "AM"]},
    ]

    resultado = pdf_suite.pdf_criar_formulario(
        _ctx(tmp_path), json.dumps(campos), 1, str(destino)
    )

    assert "erro" not in resultado
    assert set(PdfReader(str(destino)).get_fields()) == {"nome_completo", "aceito", "estado"}


def test_pdf_workflow_salva_e_executa_cadeia_de_ferramentas(tmp_path):
    import json

    origem = tmp_path / "entrada.pdf"
    copia = tmp_path / "copia.pdf"
    _criar_pdf(origem, ["WORKFLOW"])

    etapas = [{"ferramenta": "pdf_copiar",
               "argumentos": {"arquivo": str(origem), "destino": str(copia)}}]
    salvo = pdf_suite.pdf_workflow(_ctx(tmp_path), "salvar", "copiar_pdf",
                                   json.dumps(etapas))
    executado = pdf_suite.pdf_workflow(_ctx(tmp_path), "executar", "copiar_pdf")

    assert "erro" not in salvo and "erro" not in executado
    assert copia.is_file()
    assert "WORKFLOW" in PdfReader(str(copia)).pages[0].extract_text()


def test_pdf_para_word_ocr_converte_texto_nativo_em_docx(tmp_path):
    from docx import Document

    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "saida.docx"
    _criar_pdf(origem, ["TEXTO EDITAVEL"])

    resultado = pdf_suite.pdf_para_word_ocr(
        _ctx(tmp_path), str(origem), "por", str(destino)
    )

    assert "erro" not in resultado
    texto = "\n".join(p.text for p in Document(str(destino)).paragraphs)
    assert "TEXTO EDITAVEL" in texto


def test_pdf_extrair_imagens_gera_zip(tmp_path):
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    import zipfile

    imagem = tmp_path / "figura.png"
    Image.new("RGB", (80, 80), "white").save(imagem)
    origem = tmp_path / "com_imagem.pdf"
    c = canvas.Canvas(str(origem))
    c.drawImage(ImageReader(str(imagem)), 50, 50, width=80, height=80)
    c.save()

    resultado = pdf_suite.pdf_extrair_imagens(_ctx(tmp_path), str(origem))

    assert "erro" not in resultado
    with zipfile.ZipFile(resultado["zip"]) as pacote:
        assert len(pacote.namelist()) >= 1


def test_pdf_imagens_para_pdf_modo_scan_preto_branco(tmp_path):
    from PIL import Image

    imagem = tmp_path / "foto.png"
    destino = tmp_path / "digitalizado.pdf"
    Image.new("RGB", (100, 140), (220, 220, 220)).save(imagem)

    resultado = pdf_suite.pdf_imagens_para_pdf(
        _ctx(tmp_path), str(imagem), str(destino), "auto", 18, "preto_branco"
    )

    assert "erro" not in resultado
    assert resultado["modo"] == "preto_branco"
    assert len(PdfReader(str(destino)).pages) == 1


def test_pdf_unir_documentos_aceita_pdf_e_imagem(tmp_path):
    from PIL import Image

    origem_pdf = tmp_path / "texto.pdf"
    imagem = tmp_path / "foto.png"
    destino = tmp_path / "unido.pdf"
    _criar_pdf(origem_pdf, ["PAGINA PDF"])
    Image.new("RGB", (80, 120), "white").save(imagem)

    resultado = pdf_suite.pdf_unir_documentos(
        _ctx(tmp_path), f"{origem_pdf};{imagem}", str(destino)
    )

    assert "erro" not in resultado
    assert resultado["paginas"] == 2
    assert len(PdfReader(str(destino)).pages) == 2


def test_pdf_documento_para_pdf_informa_libreoffice_ausente(tmp_path, monkeypatch):
    arquivo = tmp_path / "relatorio.docx"
    arquivo.write_bytes(b"arquivo de teste")
    monkeypatch.setattr(pdf_suite.shutil, "which", lambda nome: None)

    resultado = pdf_suite.pdf_documento_para_pdf(_ctx(tmp_path), str(arquivo))

    assert "LibreOffice" in resultado["erro"]

def test_pdf_dividir_pares_impares_preserva_texto(tmp_path):
    origem = tmp_path / "origem.pdf"
    impares = tmp_path / "impares.pdf"
    pares = tmp_path / "pares.pdf"
    _criar_pdf(origem, ["PAGINA UM", "PAGINA DOIS", "PAGINA TRES", "PAGINA QUATRO"])

    resultado = pdf_suite.pdf_dividir_pares_impares(
        _ctx(tmp_path), str(origem), str(impares), str(pares)
    )

    assert "erro" not in resultado
    assert resultado["paginas_impares"] == 2
    assert resultado["paginas_pares"] == 2
    assert [p.extract_text().strip() for p in PdfReader(impares).pages] == [
        "PAGINA UM", "PAGINA TRES"
    ]
    assert [p.extract_text().strip() for p in PdfReader(pares).pages] == [
        "PAGINA DOIS", "PAGINA QUATRO"
    ]


def test_pdf_paginas_por_folha_preserva_texto_e_reduz_folhas(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "duas_por_folha.pdf"
    _criar_pdf(origem, ["PAGINA UM", "PAGINA DOIS", "PAGINA TRES"])

    resultado = pdf_suite.pdf_paginas_por_folha(
        _ctx(tmp_path), str(origem), 2, str(destino)
    )

    assert "erro" not in resultado
    leitor = PdfReader(destino)
    assert len(leitor.pages) == 2
    assert all(p.extract_text().strip() for p in leitor.pages)


def test_pdf_imprimir_livreto_cria_imposicao_frente_verso(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "livreto.pdf"
    _criar_pdf(origem, ["PAGINA UM", "PAGINA DOIS", "PAGINA TRES", "PAGINA QUATRO"])

    resultado = pdf_suite.pdf_imprimir_livreto(_ctx(tmp_path), str(origem), str(destino))

    assert "erro" not in resultado
    leitor = PdfReader(destino)
    assert len(leitor.pages) == 2
    assert "PAGINA QUATRO" in leitor.pages[0].extract_text()
    assert "PAGINA UM" in leitor.pages[0].extract_text()
    assert "PAGINA DOIS" in leitor.pages[1].extract_text()
    assert "PAGINA TRES" in leitor.pages[1].extract_text()


def test_pdf_ajustar_cores_gera_copia_rasterizada(tmp_path):
    origem = tmp_path / "origem.pdf"
    destino = tmp_path / "cinza.pdf"
    _criar_pdf(origem, ["TESTE CORES"])
    resultado = pdf_suite.pdf_ajustar_cores(_ctx(tmp_path), str(origem), "cinza", str(destino))
    assert "erro" not in resultado
    assert resultado["texto_selecionavel"] is False
    assert len(PdfReader(destino).pages) == 1
    assert origem.is_file()


def test_pdf_ajustar_cores_rejeita_modo_invalido(tmp_path):
    origem = tmp_path / "origem.pdf"
    _criar_pdf(origem, ["TESTE"])
    resultado = pdf_suite.pdf_ajustar_cores(_ctx(tmp_path), str(origem), "azul")
    assert "erro" in resultado and "cinza ou inverter" in resultado["erro"]


def test_pdf_gerar_senha_tem_comprimento_e_classes(tmp_path):
    resultado = pdf_suite.pdf_gerar_senha(_ctx(tmp_path), 24)
    senha = resultado["senha"]
    assert len(senha) == 24
    assert any(c.islower() for c in senha)
    assert any(c.isupper() for c in senha)
    assert any(c.isdigit() for c in senha)
    assert any(c in "!@#$%&*+-_=?" for c in senha)
    assert pdf_suite.pdf_gerar_senha(_ctx(tmp_path), 2)["tamanho"] == 12
