from optimus import modulos


def test_inventario_inclui_core_e_integracoes_opcionais(monkeypatch):
    monkeypatch.setattr(modulos.shutil, "which", lambda _nome: None)
    monkeypatch.setattr(modulos, "_http", lambda _url: False)
    monkeypatch.setattr(modulos, "_processo", lambda *_termos: False)
    monkeypatch.setattr(modulos, "_kiwix", lambda: {
        "id": "Kiwix", "nome": "Kiwix", "estado": "nao_instalado",
        "detalhe": "Nenhum executável", "executavel": False,
    })

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
    monkeypatch.setattr(modulos, "_processo", lambda *_termos: True)
    monkeypatch.setattr(modulos, "_kiwix", lambda: {
        "id": "Kiwix", "nome": "Kiwix", "estado": "disponivel",
        "detalhe": "Servidor gerenciado ativo", "executavel": True,
    })
    monkeypatch.setattr(modulos.subprocess, "run", lambda *a, **k:
        __import__("subprocess").CompletedProcess(a[0], 0, "27.0", ""))

    itens = {item["id"]: item for item in modulos.inventario()}

    assert itens["Kiwix"]["estado"] == "disponivel"
    assert itens["Qdrant"]["estado"] == "disponivel"


def test_inventario_distingue_instalado_parado(monkeypatch):
    monkeypatch.setattr(modulos.shutil, "which", lambda nome: "/usr/bin/" + nome)
    monkeypatch.setattr(modulos, "_http", lambda _url: False)
    monkeypatch.setattr(modulos, "_processo", lambda *_termos: False)
    monkeypatch.setattr(modulos, "_kiwix", lambda: {
        "id": "Kiwix", "nome": "Kiwix", "estado": "instalado_parado",
        "detalhe": "Instalado em pasta privada", "executavel": True,
    })
    monkeypatch.setattr(modulos.subprocess, "run", lambda *a, **k:
        __import__("subprocess").CompletedProcess(a[0], 1, "", "daemon indisponível"))

    itens = {item["id"]: item for item in modulos.inventario()}

    assert itens["Kiwix"]["estado"] == "instalado_parado"


def test_recursos_retorna_metricas_sem_caminhos_pessoais(monkeypatch):
    dados = modulos.recursos()
    assert 0 <= dados["cpu_percentual"] <= 100
    assert dados["memoria_total_bytes"] > 0
    assert dados["memoria_disponivel_bytes"] >= 0
    assert dados["cpu_nucleos_logicos"] >= 1
    assert "home" not in str(dados).lower()


def test_kiwix_inventario_reconhece_instalacao_privada(monkeypatch):
    from optimus import kiwix

    monkeypatch.setattr(kiwix, "estado", lambda: {
        "instalado": True, "gerenciado": True, "executavel_disponivel": True,
        "executando": False, "versao": "3.8.2",
    })
    item = modulos._kiwix()
    assert item["estado"] == "instalado_parado"
    assert item["gerenciado"] is True
    assert "pasta privada" in item["detalhe"]


def test_docker_nao_e_disponivel_apenas_por_ter_processo(monkeypatch):
    monkeypatch.setattr(modulos.shutil, "which", lambda _nome: "/usr/bin/docker")
    monkeypatch.setattr(modulos.subprocess, "run", lambda *a, **k:
        __import__("subprocess").CompletedProcess(a[0], 1, "", "Cannot connect to daemon"))
    item = modulos._docker()
    assert item["estado"] == "instalado_parado"
    assert "daemon indisponível" in item["detalhe"]


def test_kolibri_exige_healthcheck_e_processo(monkeypatch):
    monkeypatch.setattr(modulos.shutil, "which", lambda _nome: "/usr/bin/kolibri")
    monkeypatch.setattr(modulos, "_http", lambda _url: True)
    monkeypatch.setattr(modulos, "_processo", lambda *_termos: False)
    sem_processo = modulos._servico(
        "Kolibri", "Plataforma", ("kolibri",), "127.0.0.1", 8080,
        "http://127.0.0.1:8080/", processos=("kolibri",),
    )
    assert sem_processo["estado"] == "instalado_parado"

    monkeypatch.setattr(modulos, "_processo", lambda *_termos: True)
    ativo = modulos._servico(
        "Kolibri", "Plataforma", ("kolibri",), "127.0.0.1", 8080,
        "http://127.0.0.1:8080/", processos=("kolibri",),
    )
    assert ativo["estado"] == "disponivel"
