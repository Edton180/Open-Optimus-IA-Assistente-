from optimus import zim_catalog


def test_catalogo_mostra_todas_as_categorias_e_niveis(tmp_path, monkeypatch):
    pasta = tmp_path / "biblioteca_zim"
    pasta.mkdir()
    (pasta / "wikibooks_en_all_nopic_2026-10.zim").write_bytes(b"zim")
    monkeypatch.setattr(zim_catalog.zim, "pasta_biblioteca", lambda: pasta)

    dados = zim_catalog.catalogo()

    assert len(dados["categories"]) >= 5
    assert dados["total_recursos"] > 20
    assert {tier["name"] for categoria in dados["categories"]
            for tier in categoria["tiers"]} == {"Essential", "Standard", "Comprehensive"}
    recurso = next(
        recurso for categoria in dados["categories"]
        for tier in categoria["tiers"] for recurso in tier["resources"]
        if recurso["arquivo"] == "wikibooks_en_all_nopic_2026-10.zim"
    )
    assert recurso["instalado"] is True
    assert dados["total_instalados"] >= 1


def test_catalogo_nao_marca_arquivo_ausente_como_instalado(tmp_path, monkeypatch):
    pasta = tmp_path / "biblioteca_zim"
    pasta.mkdir()
    monkeypatch.setattr(zim_catalog.zim, "pasta_biblioteca", lambda: pasta)

    dados = zim_catalog.catalogo()

    assert dados["total_instalados"] == 0
    assert all(
        not recurso["instalado"]
        for categoria in dados["categories"]
        for tier in categoria["tiers"] for recurso in tier["resources"]
    )
