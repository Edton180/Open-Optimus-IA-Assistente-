from optimus.smart_home import home_assistant as ha


def test_estado_sem_docker(monkeypatch):
    monkeypatch.setattr(ha, "_comando_docker", lambda: None)
    d = ha.estado()
    assert d["runtime"]["docker_instalado"] is False
    assert d["container"]["estado"] == "runtime_indisponivel"


def test_detecta_container_rodando(monkeypatch):
    monkeypatch.setattr(ha, "_runtime", lambda: {
        "sistema": "Linux", "suportado": True, "docker_instalado": True,
        "docker_ativo": True, "docker_versao": "26", "metodo": "Docker Engine",
        "observacao": ""})
    monkeypatch.setattr(ha, "_container", lambda: {
        "instalado": True, "estado": "running", "rodando": True, "imagem": ha.IMAGEM})
    d = ha.estado()
    assert d["container"]["rodando"]
    assert d["url"].endswith(":8123")


def test_backup_preserva_dados(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "pasta_base", lambda: tmp_path)
    monkeypatch.setattr(ha, "_pasta", lambda: tmp_path / "home_assistant")
    (tmp_path / "home_assistant").mkdir()
    (tmp_path / "home_assistant" / "configuration.yaml").write_text("homeassistant:\n")
    r = ha.acao("backup")
    assert r["ok"]
    assert (tmp_path / "home_assistant" / "configuration.yaml").exists()
    assert (tmp_path / "backups" / Path(r["arquivo"]).name).exists()


def test_acao_desconhecida():
    try:
        ha.acao("formatar_pc")
        assert False
    except ValueError:
        pass
