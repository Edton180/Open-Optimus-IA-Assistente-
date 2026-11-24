"""Testes da biblioteca local de documentos."""
import pytest

from optimus import biblioteca
from optimus.banco import Banco
from optimus.tools import biblioteca as tbib
from optimus.tools.base import Contexto


def _banco(tmp_path):
    return Banco(tmp_path / "db.sqlite")


def _doc(pasta, nome, texto):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_text(texto, encoding="utf-8")


def test_indexa_pasta_e_pesquisa(tmp_path):
    docs = tmp_path / "docs"
    _doc(docs, "manual.md", "# Manual\n\nPara reiniciar o roteador, tire da tomada por 30s.")
    _doc(docs, "notas.txt", "A reunião de sexta foi adiada para segunda.")
    banco = _banco(tmp_path)
    resumo = biblioteca.indexar_pasta(banco, docs, estado_arq=tmp_path / "estado.json")
    assert resumo["indexados"] == 2
    assert resumo["total"] == 2
    assert banco.consultar("reiniciar roteador tomada")
    achados = banco.consultar("reunião adiada segunda")
    assert achados and achados[0]["fonte"].startswith("biblioteca:")


def test_ignora_extensao_desconhecida(tmp_path):
    docs = tmp_path / "docs"
    _doc(docs, "bom.md", "conteúdo indexável")
    _doc(docs, "imagem.png", "não indexar")
    resumo = biblioteca.indexar_pasta(_banco(tmp_path), docs, estado_arq=tmp_path / "estado.json")
    assert resumo["total"] == 1


def test_recursivo_e_idempotencia(tmp_path):
    docs = tmp_path / "docs"
    _doc(docs, "raiz.md", "na raiz")
    _doc(docs / "sub", "fundo.md", "na subpasta")
    banco = _banco(tmp_path)
    estado = tmp_path / "estado.json"
    assert biblioteca.indexar_pasta(banco, docs, recursivo=False, estado_arq=estado)["total"] == 1
    assert biblioteca.indexar_pasta(banco, docs, estado_arq=estado)["indexados"] == 2
    assert biblioteca.indexar_pasta(banco, docs, estado_arq=estado)["indexados"] == 0


def test_remove_arquivo_realmente_excluido(tmp_path):
    docs = tmp_path / "docs"
    _doc(docs, "a.md", "conteúdo A")
    _doc(docs, "b.md", "conteúdo B")
    banco = _banco(tmp_path)
    estado = tmp_path / "estado.json"
    biblioteca.indexar_pasta(banco, docs, estado_arq=estado)
    (docs / "b.md").unlink()
    resumo = biblioteca.indexar_pasta(banco, docs, estado_arq=estado)
    assert resumo["removidos"] == 1
    assert not any(f["fonte"].endswith("b.md") for f in biblioteca.fontes(banco))


def test_arquivo_esvaziado_sai_do_indice(tmp_path):
    docs = tmp_path / "docs"
    _doc(docs, "a.md", "conteúdo que será apagado depois")
    banco = _banco(tmp_path)
    estado = tmp_path / "estado.json"
    biblioteca.indexar_pasta(banco, docs, estado_arq=estado)
    (docs / "a.md").write_text("", encoding="utf-8")
    resumo = biblioteca.indexar_pasta(banco, docs, estado_arq=estado)
    assert resumo["ignorados"] == 1
    assert biblioteca.fontes(banco) == []
    assert not banco.consultar("conteúdo apagado depois")


def test_pasta_inexistente_nunca_apaga_indice(tmp_path):
    docs = tmp_path / "docs"
    _doc(docs, "a.md", "conteúdo preservado")
    banco = _banco(tmp_path)
    estado = tmp_path / "estado.json"
    biblioteca.indexar_pasta(banco, docs, estado_arq=estado)
    with pytest.raises(FileNotFoundError):
        biblioteca.indexar_pasta(banco, tmp_path / "desconectada", estado_arq=estado)
    assert len(biblioteca.fontes(banco)) == 1
    assert banco.consultar("conteúdo preservado")


def test_arquivo_acima_limite_preserva_versao_indexada(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    _doc(docs, "a.md", "conteúdo antigo")
    banco = _banco(tmp_path)
    estado = tmp_path / "estado.json"
    biblioteca.indexar_pasta(banco, docs, estado_arq=estado)
    monkeypatch.setattr(biblioteca, "MAX_BYTES", 1)
    resumo = biblioteca.indexar_pasta(banco, docs, estado_arq=estado)
    assert resumo["indexados"] == 0
    assert resumo["erros"] and "limite" in resumo["erros"][0]["erro"]
    assert banco.consultar("conteúdo antigo")


def test_docx_indexa_paragrafos_e_tabelas(tmp_path):
    docx = pytest.importorskip("docx")
    docs = tmp_path / "docs"
    docs.mkdir()
    documento = docx.Document()
    documento.add_paragraph("Manual de manutenção preventiva")
    tabela = documento.add_table(rows=1, cols=2)
    tabela.rows[0].cells[0].text = "Periodicidade"
    tabela.rows[0].cells[1].text = "A cada seis meses"
    documento.save(docs / "manual.docx")
    banco = _banco(tmp_path)
    resumo = biblioteca.indexar_pasta(banco, docs, estado_arq=tmp_path / "estado.json")
    assert resumo["indexados"] == 1
    assert banco.consultar("manutenção preventiva")
    assert banco.consultar("periodicidade seis meses")


def test_ferramentas_agente(tmp_path):
    docs = tmp_path / "docs"
    _doc(docs, "a.md", "conteúdo indexável pela ferramenta")
    banco = _banco(tmp_path)
    ctx = Contexto(config=None, banco=banco, pasta_trabalho=tmp_path)
    resposta = tbib.biblioteca_indexar(ctx, str(docs))
    assert resposta["indexados"] == 1 and "mensagem" in resposta
    assert tbib.biblioteca_listar(ctx)["total"] == 1


def test_ferramenta_pasta_inexistente(tmp_path):
    ctx = Contexto(config=None, banco=_banco(tmp_path), pasta_trabalho=tmp_path)
    resposta = tbib.biblioteca_indexar(ctx, str(tmp_path / "nao_existe"))
    assert "erro" in resposta
