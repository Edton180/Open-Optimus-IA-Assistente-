from optimus import zim


def test_lista_arquivos_zim_sem_expor_caminho(tmp_path, monkeypatch):
    pasta = tmp_path / "zim"
    pasta.mkdir()
    (pasta / "wikipedia_pt.zim").write_bytes(b"zim-data")
    (pasta / "LEARN.ZIM").write_bytes(b"abc")
    (pasta / "nao-e-zim.pdf").write_bytes(b"pdf")
    (pasta / "subpasta").mkdir()
    monkeypatch.setattr(zim, "pasta_biblioteca", lambda: pasta)

    dados = zim.listar_zim()

    assert dados["total"] == 2
    assert dados["tamanho_total_bytes"] == 11
    assert [item["nome"] for item in dados["arquivos"]] == ["LEARN.ZIM", "wikipedia_pt.zim"]
    assert "caminho" not in str(dados).lower()
    assert "tmp_path" not in str(dados)


def test_lista_ignora_link_simbolico(tmp_path, monkeypatch):
    pasta = tmp_path / "zim"
    pasta.mkdir()
    externo = tmp_path / "fora.zim"
    externo.write_bytes(b"conteudo")
    try:
        (pasta / "atalho.zim").symlink_to(externo)
    except (OSError, NotImplementedError):
        return
    monkeypatch.setattr(zim, "pasta_biblioteca", lambda: pasta)

    assert zim.listar_zim()["total"] == 0


def test_lista_cria_pasta_gerenciada(tmp_path, monkeypatch):
    pasta = tmp_path / "dados" / "biblioteca_zim"
    monkeypatch.setattr(zim, "pasta_biblioteca", lambda: pasta)

    dados = zim.listar_zim()

    assert pasta.is_dir()
    assert dados["pasta_configurada"] is True
    assert dados["arquivos"] == []
