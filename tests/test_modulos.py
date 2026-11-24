from optimus import modulos


def test_inventario_inclui_core_e_integracoes_opcionais(monkeypatch):
    monkeypatch.setattr(modulos.shutil, "which", lambda _nome: None)
    monkeypatch.setattr(modulos, "_http", lambda _url: False)
    monkeypatch.setattr(modulos, "_processo", lambda _host, _port: False)

    itens = modulos.inventario()
    por_id = {item["id"]: item for item in itens}

    assert por_id["Optimus Core"]["estado"] == "nativo"
    assert por_id["Kiwix"]["estado"] == "nao_instalado"
    assert por_id["Kolibri"]["estado"] == "nao_instalado"
    assert por_id["Qdrant"]["estado"] == "nao_instalado"
    assert por_id["Docker"]["estado"] == "nao_instalado"


def test_inventario_identifica_servico_respondendo(monkeypatch):
    monkeypatch.setattr(modulos.shutil, "which", lambda nome: "/usr/bin/" + nome)
    monkeypatch.setattr(modulos, "_http", lambda _url: True)
    monkeypatch.setattr(modulos, "_porta", lambda _host, _port: True)

    itens = {item["id"]: item for item in modulos.inventario()}

    assert itens["Kiwix"]["estado"] == "disponivel"
    assert itens["Qdrant"]["estado"] == "disponivel"


def test_inventario_distingue_instalado_parado(monkeypatch):
    monkeypatch.setattr(modulos.shutil, "which", lambda nome: "/usr/bin/" + nome)
    monkeypatch.setattr(modulos, "_http", lambda _url: False)
    monkeypatch.setattr(modulos, "_porta", lambda _host, _port: False)

    itens = {item["id"]: item for item in modulos.inventario()}

    assert itens["Kiwix"]["estado"] == "instalado_parado"
