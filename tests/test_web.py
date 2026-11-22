import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

from optimus.app import Optimus
from optimus.config import Config
from optimus.engine.demo import MotorDemo
from optimus.web import server


def _subir(senha=""):
    config = Config()
    config.definir("motor", "backend", "demo")
    config.definir("web", "senha", senha)
    optimus = Optimus(config)
    optimus.motor = MotorDemo()
    server.Manipulador.estado = server.Estado(optimus)
    server.Manipulador.senha = senha
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Manipulador)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _req(url, dados=None, cab=None):
    corpo = json.dumps(dados).encode() if dados is not None else None
    pedido = urllib.request.Request(url, data=corpo, headers={"Content-Type": "application/json",
                                                              **(cab or {})})
    with urllib.request.urlopen(pedido, timeout=10) as r:
        return json.loads(r.read())


def test_fluxo_de_conversa_pela_interface():
    httpd, base = _subir()
    try:
        assert "OPTIMUS" in urllib.request.urlopen(base + "/").read().decode()
        estado = _req(base + "/api/estado")
        assert estado["motor"]["disponivel"] and estado["perfil"]["modelo"]
        tarefa = _req(base + "/api/enviar", {"texto": "que dia é hoje"})["tarefa"]
        for _ in range(50):
            dados = _req(f"{base}/api/tarefa/{tarefa}")
            if dados["terminou"]:
                break
            time.sleep(0.1)
        finais = [e for e in dados["eventos"] if e["tipo"] == "final"]
        assert finais and "São" in finais[0]["texto"]
        conversas = _req(base + "/api/conversas")["conversas"]
        assert conversas[0]["titulo"].startswith("que dia")
        config = _req(base + "/api/config")["config"]
        assert config["motor"]["backend"] == "demo"
    finally:
        httpd.shutdown()


def test_confirmacao_pela_interface(tmp_path):
    alvo = tmp_path / "apagar.txt"
    alvo.write_text("x")
    httpd, base = _subir()
    try:
        tarefa = _req(base + "/api/enviar", {"texto": f"apague o arquivo {alvo}"})["tarefa"]
        for _ in range(50):
            dados = _req(f"{base}/api/tarefa/{tarefa}")
            if dados["pendente"]:
                break
            time.sleep(0.1)
        assert dados["pendente"]["nome"] == "apagar"
        _req(base + "/api/confirmar", {"tarefa": tarefa, "aprovar": True})
        for _ in range(50):
            if _req(f"{base}/api/tarefa/{tarefa}")["terminou"]:
                break
            time.sleep(0.1)
        assert not alvo.exists()
    finally:
        httpd.shutdown()


def test_senha_protege_a_api():
    httpd, base = _subir(senha="segredo")
    try:
        try:
            _req(base + "/api/estado")
            assert False, "deveria pedir senha"
        except urllib.error.HTTPError as erro:
            assert erro.code == 401
        assert _req(base + "/api/estado", cab={"X-Optimus-Senha": "segredo"})["versao"]
    finally:
        httpd.shutdown()


def test_rota_de_atualizacao_responde(tmp_path):
    # A rota existe e devolve o estado do updater (aqui, fora de um repo Git, um erro tratado).
    httpd, base = _subir()
    try:
        try:
            d = _req(base + "/api/atualizacao")
            assert "atualizado" in d or "erro" in d
        except urllib.error.HTTPError as erro:
            # Sem repositório Git: a rota responde 503 com {"erro": ...}, não 404.
            assert erro.code == 503
    finally:
        httpd.shutdown()


def test_adicionar_e_remover_camera_ip(tmp_path):
    httpd, base = _subir()
    try:
        cab = {"X-Optimus-Senha": ""}
        _req(base + "/api/cameras", {"nome": "Portão", "url": "192.168.0.30",
                                     "usuario": "admin", "senha": "1234"}, cab)
        cams = _req(base + "/api/cameras", cab=cab)["cameras"]
        assert any(c["nome"] == "Portão" and c["id"] == "ip:0" for c in cams)
        # Remover pela id ip:0.
        pedido = urllib.request.Request(base + "/api/cameras/ip:0", method="DELETE",
                                        headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(pedido, timeout=10) as r:
            assert json.load(r)["ok"]
        assert not _req(base + "/api/cameras", cab=cab)["cameras"]
    finally:
        httpd.shutdown()
