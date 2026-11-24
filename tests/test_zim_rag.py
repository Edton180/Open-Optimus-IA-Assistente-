from __future__ import annotations

import sys
import types

from optimus import zim_rag


def test_html_extraction_ignores_script_and_style():
    texto = zim_rag._texto(
        b"<html><head><style>nao indexar</style></head><body>"
        b"<h1>Seguranca do trabalho</h1><p>Use equipamento de protecao.</p>"
        b"<script>alert('x')</script></body></html>"
    )
    assert "Seguranca do trabalho" in texto
    assert "equipamento de protecao" in texto
    assert "nao indexar" not in texto
    assert "alert" not in texto


def test_chunks_have_overlap_and_are_bounded():
    texto = " ".join(f"palavra{i}" for i in range(500))
    partes = zim_rag._chunks(texto)
    assert len(partes) >= 3
    assert all(len(p) <= zim_rag.TAMANHO_CHUNK for p in partes)
    assert set(partes[0].split()[-5:]) & set(partes[1].split()[:20])


def test_sqlite_fts_and_source_citation(tmp_path, monkeypatch):
    monkeypatch.setattr(zim_rag, "_pasta", lambda: tmp_path)
    con = zim_rag._db()
    try:
        con.execute(
            "INSERT INTO trechos(arquivo,caminho_artigo,titulo,url,posicao,texto,hash,embedding) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ("wikipedia_pt.zim", "Seguranca_do_trabalho", "Segurança do trabalho",
             "zim://wikipedia_pt.zim/Seguranca_do_trabalho", 0,
             "Equipamentos de proteção individual reduzem riscos ocupacionais.",
             "abc", None),
        )
        con.commit()
    finally:
        con.close()
    resultados = zim_rag.buscar("equipamentos proteção individual", limite=5)
    assert resultados
    assert resultados[0]["arquivo"] == "wikipedia_pt.zim"
    assert resultados[0]["artigo"] == "Seguranca_do_trabalho"
    assert resultados[0]["url"].startswith("zim://")
    assert "Segurança do trabalho" in resultados[0]["citacao"]


def test_incremental_index_resume_and_complete(tmp_path, monkeypatch):
    pasta_zim = tmp_path / "biblioteca_zim"
    pasta_zim.mkdir()
    arquivo_zim = pasta_zim / "pequeno.zim"
    arquivo_zim.write_bytes(b"zim-fixture")
    pasta_indice = tmp_path / "indice"
    pasta_indice.mkdir()
    monkeypatch.setattr(zim_rag, "_pasta", lambda: pasta_indice)
    monkeypatch.setattr("optimus.zim.pasta_biblioteca", lambda: pasta_zim)

    class Item:
        mimetype = "text/html"
        size = 120
        content = b"<html><h1>Artigo de teste</h1><p>Conteudo de teste para indexacao incremental.</p></html>"

    class Entry:
        title = "Artigo de teste"
        path = "Artigo_de_teste"
        is_redirect = False

        def get_item(self):
            return Item()

    class Archive:
        all_entry_count = 1

        def __init__(self, _path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            return iter([Entry()])

    libzim = types.ModuleType("libzim")
    reader = types.ModuleType("libzim.reader")
    reader.Archive = Archive
    libzim.reader = reader
    monkeypatch.setitem(sys.modules, "libzim", libzim)
    monkeypatch.setitem(sys.modules, "libzim.reader", reader)

    primeira = zim_rag.indexar(limite=1)
    assert primeira["artigos_processados"] == 1
    assert primeira["estado"]["trechos"] == 1
    segunda = zim_rag.indexar(limite=1)
    assert segunda["estado"]["arquivos"][0]["concluido"] == 1
    assert segunda["estado"]["artigos_indexados"] == 1


def test_libzim_3x_iterator_fallback_uses_entry_id():
    class ArchiveAntigo:
        entry_count = 3

        def get_entry_by_id(self, indice):
            return f"artigo-{indice}"

    assert list(zim_rag._iterar_entradas(ArchiveAntigo())) == [
        "artigo-0", "artigo-1", "artigo-2"
    ]


def test_libzim_4x_prefers_efficient_iterator():
    class ArchiveNovo:
        def iter_efficient(self):
            return iter(["a", "b"])

        def __iter__(self):
            raise AssertionError("deve usar o iterador eficiente")

    assert list(zim_rag._iterar_entradas(ArchiveNovo())) == ["a", "b"]



def test_real_zim_roundtrip_and_article_index(tmp_path, monkeypatch):
    import pytest

    writer = pytest.importorskip("libzim.writer")
    caminho = tmp_path / "biblioteca_zim"
    caminho.mkdir()
    zim_file = caminho / "fixture.zim"
    indice = tmp_path / "indice"
    indice.mkdir()
    monkeypatch.setattr(zim_rag, "_pasta", lambda: indice)
    monkeypatch.setattr("optimus.zim.pasta_biblioteca", lambda: caminho)
    monkeypatch.setattr(zim_rag, "_modelo_auto", lambda *args: "")
    monkeypatch.setattr(zim_rag, "_embedding", lambda *args: None)

    class Artigo(writer.Item):
        def __init__(self):
            super().__init__()
            self.path = "index"
            self.title = "Guia de segurança"
            self.conteudo = (
                "<html><head><title>Guia</title></head><body>"
                "<h1>Segurança do trabalho</h1>"
                "<p>Use equipamento de proteção individual e siga o procedimento de bloqueio.</p>"
                "</body></html>"
            )

        def get_path(self):
            return self.path

        def get_title(self):
            return self.title

        def get_mimetype(self):
            return "text/html"

        def get_contentprovider(self):
            return writer.StringProvider(self.conteudo)

        def get_hints(self):
            hint = getattr(writer, "Hint", None)
            return {hint.FRONT_ARTICLE: True} if hint else {}

    creator = writer.Creator(str(zim_file))
    configurar = getattr(creator, "config_indexing", None) or getattr(creator, "configIndexing", None)
    if configurar:
        configurar(True, "eng")
    with creator:
        set_main = getattr(creator, "set_mainpath", None) or getattr(creator, "setMainPath", None)
        if set_main:
            set_main("index")
        creator.add_item(Artigo())

    from optimus import zim
    stat = zim_file.stat()
    monkeypatch.setattr(zim, "listar_zim", lambda: {
        "arquivos": [{"nome": "fixture.zim", "tamanho_bytes": stat.st_size,
                      "modificado_em": int(stat.st_mtime)}]
    })
    resultado = zim_rag.indexar(limite=100)
    assert resultado["indexados"] == 1, resultado
    encontrados = zim_rag.buscar("equipamento proteção individual", limite=3)
    assert encontrados
    assert encontrados[0]["arquivo"] == "fixture.zim"
    assert encontrados[0]["artigo"]
    assert encontrados[0]["url"].startswith("zim://fixture.zim/")



def test_embedding_discovery_never_probes_remote_endpoint(monkeypatch):
    import httpx

    def nao_deve_chamar(*_args, **_kwargs):
        raise AssertionError("não deve consultar endpoints remotos")

    monkeypatch.setattr(httpx, "get", nao_deve_chamar)
    assert zim_rag._modelo_auto("https://api.exemplo.com", "all-minilm") == ""
    resultado = zim_rag.preparar_embedding("https://api.exemplo.com")
    assert resultado["instalado"] is False
    assert "modo lexical" in resultado["erro"]


def test_embedding_uses_existing_local_model_without_download(monkeypatch):
    monkeypatch.setattr(zim_rag, "_modelo_auto", lambda *_args: "nomic-embed-text:latest")
    resultado = zim_rag.preparar_embedding("http://127.0.0.1:11434")
    assert resultado == {
        "instalado": True,
        "modelo": "nomic-embed-text:latest",
        "origem": "existente",
    }

def test_real_zim_archive_round_trip(tmp_path, monkeypatch):
    import pytest

    writer = pytest.importorskip("libzim.writer")
    Creator, Item, StringProvider, Hint = (
        writer.Creator, writer.Item, writer.StringProvider, writer.Hint
    )

    class Artigo(Item):
        def __init__(self):
            super().__init__()
            self.path = "artigo-seguranca"
            self.title = "Segurança do trabalho"
            self.conteudo = (
                "<html><meta charset='utf-8'><h1>Segurança do trabalho</h1>"
                "<p>Equipamentos de proteção individual reduzem riscos ocupacionais.</p></html>"
            )

        def get_path(self):
            return self.path

        def get_title(self):
            return self.title

        def get_mimetype(self):
            return "text/html"

        def get_contentprovider(self):
            return StringProvider(self.conteudo)

        def get_hints(self):
            return {Hint.FRONT_ARTICLE: True}

    pasta_zim = tmp_path / "biblioteca_zim"
    pasta_zim.mkdir()
    caminho = pasta_zim / "fixture-real.zim"
    with Creator(str(caminho)) as creator:
        creator.set_mainpath("artigo-seguranca")
        creator.add_item(Artigo())
        for chave, valor in {
            "Creator": "Optimus test",
            "Name": "optimus-fixture",
            "Title": "Fixture de teste",
            "Language": "por",
            "Date": "2026-11-24",
            "Description": "Arquivo ZIM mínimo gerado durante o teste.",
            "Publisher": "Optimus",
        }.items():
            creator.add_metadata(chave, valor)

    pasta_indice = tmp_path / "indice-real"
    pasta_indice.mkdir()
    monkeypatch.setattr(zim_rag, "_pasta", lambda: pasta_indice)
    monkeypatch.setattr("optimus.zim.pasta_biblioteca", lambda: pasta_zim)

    resultado = zim_rag.indexar(limite=100)
    assert resultado["indexados"] >= 1
    encontrados = zim_rag.buscar("equipamentos proteção individual")
    assert encontrados
    assert encontrados[0]["arquivo"] == "fixture-real.zim"
    assert encontrados[0]["artigo"] == "artigo-seguranca"
    assert "zim://fixture-real.zim/artigo-seguranca" == encontrados[0]["url"]
