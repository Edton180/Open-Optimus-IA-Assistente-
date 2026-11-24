"""QR code para o celular e agenda (.ics) dos lembretes."""

import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from optimus.app import Optimus
from optimus.config import Config
from optimus.engine.demo import MotorDemo
from optimus.web import celular, server


def test_ics_valido_com_repeticao_e_escape():
    ics = celular.agenda_ics([
        {"id": 1, "texto": "Pagar a luz, hoje; sem falta", "quando": 1_800_000_000,
         "repetir_minutos": 0},
        {"id": 2, "texto": "Remédio", "quando": 1_800_003_600, "repetir_minutos": 1440},
        {"id": 3, "texto": "x" * 200, "quando": 1_800_000_000, "repetir_minutos": 90},
    ], nome="Optimus", agora=1_799_000_000)
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 3
    assert "SUMMARY:Pagar a luz\\, hoje\\; sem falta" in ics
    assert "RRULE:FREQ=DAILY;INTERVAL=1" in ics and "RRULE:FREQ=MINUTELY;INTERVAL=90" in ics
    assert "DTSTART:20270115T080000Z" in ics
    assert all(len(linha.encode()) <= 75 for linha in ics.split("\r\n"))  # dobra as longas


def test_qr_svg_e_endereco(monkeypatch):
    pytest.importorskip("segno")
    assert celular.qr_svg("http://192.168.0.10:8765").lstrip().startswith("<svg")
    monkeypatch.setattr(celular, "ip_local", lambda: "192.168.0.10")
    assert celular.endereco_rede(8765) == "http://192.168.0.10:8765"
    assert celular.endereco_rede(8765, "10.0.0.2") == "http://10.0.0.2:8765"


def test_sem_segno_mostra_so_o_link(monkeypatch):
    monkeypatch.setattr(celular, "_qr", lambda t: None)
    assert celular.qr_svg("http://x") == "" and not celular.qr_terminal("http://x")


def test_tunel_exige_senha_forte_e_cloudflared(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda nome: None)
    assert "12 caracteres" in server.iniciar_tunel(8765, "curta")["erro"]
    resultado = server.iniciar_tunel(8765, "senha-forte-de-teste")
    assert "cloudflared" in resultado["erro"]
    assert server.estado_tunel()["ligado"] is False


def _subir(senha):
    config = Config()
    config.definir("motor", "backend", "demo")
    config.definir("web", "senha", senha)
    optimus = Optimus(config)
    optimus.motor = MotorDemo()
    optimus.banco.criar_lembrete("Reunião", time.time() + 3600)
    server.Manipulador.estado = server.Estado(optimus)
    server.Manipulador.senha = senha
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Manipulador)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def test_agenda_pela_api_com_chave_do_link():
    import json

    httpd, base = _subir("s3nha")
    try:
        with pytest.raises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(base + "/api/agenda.ics?chave=errada", timeout=5)
        assert erro.value.code == 401
        pedido = urllib.request.Request(base + "/api/celular",
                                        headers={"X-Optimus-Senha": "s3nha"})
        with urllib.request.urlopen(pedido, timeout=5) as r:
            dados = json.loads(r.read())
        assert not dados["rede"] and dados["dica"]
        link = dados["agenda"].replace(dados["url"], base)
        with urllib.request.urlopen(link, timeout=5) as r:
            assert r.headers["Content-Type"].startswith("text/calendar")
            assert "SUMMARY:Reunião" in r.read().decode()
        cfg = server.Manipulador.estado.optimus.config.dados["web"]
        assert cfg["token_agenda"]  # criada na primeira vez
    finally:
        httpd.shutdown()


def test_ligar_acesso_pelo_celular_pela_interface(monkeypatch):
    import json

    httpd, base = _subir("")
    monkeypatch.setattr(server, "porta_celular", lambda config, porta: 0)  # porta livre
    try:
        def post(caminho, corpo):
            pedido = urllib.request.Request(base + caminho, data=json.dumps(corpo).encode(),
                                            headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(pedido, timeout=5) as r:
                return json.loads(r.read())

        with pytest.raises(urllib.error.HTTPError) as erro:  # sem senha não abre para a rede
            post("/api/celular", {})
        assert erro.value.code == 400
        dados = post("/api/celular", {"senha": "1234"})
        assert dados["ligado"] and dados["qr"].lstrip().startswith("<svg")
        porta = server._servidor_celular.server_address[1]
        assert dados["url"].endswith(f":{porta}")
        # a porta do celular exige a senha; com ela, responde
        with pytest.raises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/estado", timeout=5)
        assert erro.value.code == 401
        pedido = urllib.request.Request(f"http://127.0.0.1:{porta}/api/estado",
                                        headers={"X-Optimus-Senha": "1234"})
        with urllib.request.urlopen(pedido, timeout=5) as r:
            assert r.status == 200
        assert server.Manipulador.estado.optimus.config.get("web", "celular") is True
        dados = post("/api/celular/desligar", {})
        assert not dados["ligado"] and server._servidor_celular is None
    finally:
        server.desligar_celular()
        httpd.shutdown()
