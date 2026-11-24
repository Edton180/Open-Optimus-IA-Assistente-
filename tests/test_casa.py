from optimus.config import Config
from optimus.tools import casa
from optimus.tools.base import Contexto


class RespostaFake:
    def __init__(self, dados, status=200):
        self._dados = dados
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._dados


def _ctx(tmp_path, ha=True):
    config = Config()
    config.caminho = tmp_path / "config.toml"
    if ha:
        config.definir("casa", "url", "http://homeassistant.local:8123")
        config.definir("casa", "token", "token-de-teste")
    return Contexto(config=config, pasta_trabalho=tmp_path)


def test_casa_diagnostico_lista_entidades_e_cameras(monkeypatch, tmp_path):
    monkeypatch.setattr(casa.webcam, "listar", lambda: [{"indice": 0, "nome": "USB Cam"}])
    chamadas = []

    def get(url, **kwargs):
        chamadas.append((url, kwargs))
        return RespostaFake([
            {"entity_id": "light.sala", "state": "on", "attributes": {"friendly_name": "Sala"}},
            {"entity_id": "climate.quarto", "state": "cool", "attributes": {}},
            {"entity_id": "camera.portao", "state": "streaming",
             "attributes": {"friendly_name": "Portão"}},
        ])

    monkeypatch.setattr(casa.httpx, "get", get)
    resultado = casa.casa_diagnostico(_ctx(tmp_path))

    assert resultado["home_assistant_configurado"] is True
    assert resultado["home_assistant_conectado"] is True
    assert resultado["entidades"] == 3
    assert resultado["dominios"] == {"camera": 1, "climate": 1, "light": 1}
    assert resultado["cameras_home_assistant"][0]["id"] == "camera.portao"
    assert resultado["webcams"][0]["nome"] == "USB Cam"
    assert chamadas[0][1]["headers"]["Authorization"] == "Bearer token-de-teste"
    assert "VPN" in resultado["observacoes"][-1]


def test_casa_diagnostico_sem_home_assistant_nao_finge_conexao(monkeypatch, tmp_path):
    monkeypatch.setattr(casa.webcam, "listar", lambda: [])
    resultado = casa.casa_diagnostico(_ctx(tmp_path, ha=False))

    assert resultado["home_assistant_configurado"] is False
    assert resultado["home_assistant_conectado"] is False
    assert resultado["entidades"] == 0
    assert "erro_home_assistant" not in resultado


def test_casa_diagnostico_explica_falha_de_conexao(monkeypatch, tmp_path):
    monkeypatch.setattr(casa.webcam, "listar", lambda: [])
    monkeypatch.setattr(casa.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(
        TimeoutError("timeout simulado")))

    resultado = casa.casa_diagnostico(_ctx(tmp_path))

    assert resultado["home_assistant_configurado"] is True
    assert resultado["home_assistant_conectado"] is False
    assert "TimeoutError" in resultado["erro_home_assistant"]


def test_diagnostico_nao_altera_estado_de_dispositivos(monkeypatch, tmp_path):
    def proibido(*args, **kwargs):
        raise AssertionError("diagnóstico não pode executar POST")

    monkeypatch.setattr(casa.httpx, "post", proibido)
    monkeypatch.setattr(casa.httpx, "get", lambda *a, **k: RespostaFake([]))
    resultado = casa.casa_diagnostico(_ctx(tmp_path))
    assert resultado["home_assistant_conectado"] is True

def test_casa_diagnostico_configuracao_incompleta_nao_tenta_conectar(monkeypatch, tmp_path):
    monkeypatch.setattr(casa.webcam, "listar", lambda: [])
    contexto = _ctx(tmp_path, ha=False)
    contexto.config.definir("casa", "url", "http://homeassistant.local:8123")

    def proibido(*args, **kwargs):
        raise AssertionError("não deve chamar a API sem token")

    monkeypatch.setattr(casa.httpx, "get", proibido)
    resultado = casa.casa_diagnostico(contexto)

    assert resultado["home_assistant_configurado"] is False
    assert resultado["home_assistant_conectado"] is False
    assert "erro_home_assistant" not in resultado
