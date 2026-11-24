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
    monkeypatch.setattr(zim_rag, "_pasta", lambda: tmp_path / "indice")
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
