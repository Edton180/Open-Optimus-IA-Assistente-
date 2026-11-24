from pathlib import Path

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


def test_diagnostico_docker_usa_timeout_curto(monkeypatch):
    chamadas = []
    monkeypatch.setattr(ha, "_comando_docker", lambda: ["docker"])

    def executar(args, timeout=45, check=True, elevate=False):
        chamadas.append(timeout)
        return __import__("subprocess").CompletedProcess(args, 0, "26.0", "")

    monkeypatch.setattr(ha, "_executar", executar)
    estado = ha._runtime()
    assert estado["docker_ativo"] is True
    assert chamadas == [3]

    chamadas.clear()
    ha._container()
    assert chamadas == [3]



def test_container_linux_habilita_bluetooth_sem_privileged(monkeypatch, tmp_path):
    monkeypatch.setattr(ha.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ha.Path, "exists", lambda self: str(self) == "/run/dbus/system_bus_socket")
    args = ha._argumentos_container(tmp_path)
    assert "--network" in args and "host" in args
    assert "--cap-add" in args
    assert args[args.index("--cap-add") + 1] == "NET_ADMIN"
    assert args[args.index("--cap-add", args.index("--cap-add") + 1) + 1] == "NET_RAW"
    assert "/run/dbus:/run/dbus:ro" in args
    assert "--privileged" not in args


def test_container_linux_sem_dbus_nao_falha(monkeypatch, tmp_path):
    monkeypatch.setattr(ha.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ha.Path, "exists", lambda self: False)
    args = ha._argumentos_container(tmp_path)
    assert "--cap-add" in args
    assert "/run/dbus:/run/dbus:ro" not in args


def test_container_windows_nao_recebe_capacidades_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(ha.platform, "system", lambda: "Windows")
    args = ha._argumentos_container(tmp_path)
    assert "-p" in args
    assert "8123:8123" in args
    assert "--cap-add" not in args
    assert "--network" not in args
