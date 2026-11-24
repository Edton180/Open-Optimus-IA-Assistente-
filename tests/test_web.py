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
        # O status do motor é consultado em segundo plano para a API não bloquear.
        estado = _req(base + "/api/estado")
        assert estado["perfil"]["modelo"]
        for _ in range(30):
            if estado["motor"]["disponivel"]:
                break
            time.sleep(0.1)
            estado = _req(base + "/api/estado")
        assert estado["motor"]["disponivel"]
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


def test_estado_usa_cache_do_motor():
    # /api/estado é chamado em loop; o status do motor não pode bater no motor a cada poll.
    from optimus.app import Optimus
    from optimus.config import Config
    from optimus.engine.demo import MotorDemo
    from optimus.web import server

    config = Config(); config.definir("motor", "backend", "demo")
    optimus = Optimus(config)
    chamadas = {"n": 0}

    class MotorContado(MotorDemo):
        def modelos(self):
            chamadas["n"] += 1
            return super().modelos()

    optimus.motor = MotorContado()
    est = server.Estado(optimus)
    est.motor_status(); est.motor_status(); est.motor_status()
    assert chamadas["n"] == 1  # as três chamadas seguidas vêm do cache



def test_rota_tunel_existe_e_retorna_estado(monkeypatch):
    httpd, base = _subir()
    try:
        # GET do painel deve responder estado JSON; rota ausente seria 404.
        dados = _req(base + "/api/tunel")
        assert "ligado" in dados and "url" in dados
        # POST desligar é idempotente e não deve cair no fallback "rota não encontrada".
        dados = _req(base + "/api/tunel/desligar", {})
        assert "ligado" in dados and dados["ligado"] is False
    finally:
        httpd.shutdown()


def test_rota_tunel_retorna_erro_operacional_sem_404(monkeypatch):
    httpd, base = _subir()
    monkeypatch.setattr(server, "iniciar_tunel",
                        lambda porta, senha: {"erro": "cloudflared indisponível"})
    try:
        try:
            _req(base + "/api/tunel", {"senha": "senha-forte-para-testes"})
            assert False, "deveria retornar erro operacional"
        except urllib.error.HTTPError as erro:
            assert erro.code == 503
            assert json.loads(erro.read())["erro"] == "cloudflared indisponível"
    finally:
        httpd.shutdown()


def test_fluxo_pdf_upload_e_execucao_pela_interface():
    from io import BytesIO
    from pypdf import PdfWriter

    httpd, base = _subir()
    try:
        catalogo = _req(base + "/api/pdf")
        assert any(f["nome"] == "pdf_info" for f in catalogo["ferramentas"])

        buffer = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        writer.write(buffer)
        pedido = urllib.request.Request(
            base + "/api/pdf/upload?nome=teste.pdf",
            data=buffer.getvalue(),
            headers={"Content-Type": "application/pdf"},
            method="POST",
        )
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            enviado = json.loads(resposta.read())

        resultado = _req(base + "/api/pdf/executar", {
            "ferramenta": "pdf_info",
            "argumentos": {"arquivo": enviado["arquivo"]},
        })
        assert resultado["resultado"]["paginas"] == 1
    finally:
        httpd.shutdown()

def test_status_do_motor_nao_bloqueia_resposta_da_api(monkeypatch):
    """Um Ollama/servidor remoto que não responde não pode congelar a tela inicial."""
    from optimus.engine.demo import MotorDemo
    from optimus.web.server import Estado

    config = Config()
    config.definir("motor", "backend", "demo")
    optimus = Optimus(config)
    iniciou = threading.Event()
    liberar = threading.Event()

    class MotorLento(MotorDemo):
        def disponivel(self):
            iniciou.set()
            liberar.wait(timeout=2)
            return True

        def modelos(self):
            return ["modelo-teste"]

    optimus.motor = MotorLento()
    estado = Estado(optimus)
    inicio = time.monotonic()
    disponivel, modelos = estado.motor_status()
    duracao = time.monotonic() - inicio
    try:
        assert duracao < 0.2
        assert disponivel is False and modelos == []
        assert iniciou.wait(timeout=1)
    finally:
        liberar.set()



def test_boot_nao_pode_ficar_preso_e_arquivos_estaticos_nao_sao_cacheados():
    # Este teste valida somente arquivos estáticos; não precisa iniciar hardware, banco ou IA.
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Manipulador)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as resposta:
            pagina = resposta.read().decode()
        assert "boot-failsafe-aviso" in pagina
        assert "__optimusLiberarBoot" in pagina
        assert "/app.js" in pagina and "/hud.js" in pagina

        for recurso in ("app.js", "hud.js", "estudio.js", "style.css"):
            with urllib.request.urlopen(base + "/" + recurso, timeout=5) as resposta:
                assert resposta.status == 200
                assert "no-store" in resposta.headers.get("Cache-Control", "")
                assert resposta.read()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_seletor_do_menu_nao_interrompe_a_inicializacao():
    """Os dois usos do menu precisam selecionar uma coleção, não um elemento único."""
    codigo = (server.ESTATICOS / "app.js").read_text(encoding="utf-8")
    seletores_menu = [
        linha.strip()
        for linha in codigo.splitlines()
        if '".menu button"' in linha and ".forEach(" in linha
    ]
    assert len(seletores_menu) == 2
    assert all(linha.startswith('$$(".menu button")') for linha in seletores_menu)


def test_senha_nao_e_exigida_no_acesso_local_sem_rede_ou_tunel():
    """Uma senha salva para celular/rede não deve bloquear a interface no próprio PC."""
    from optimus.web.server import _senha_para_acesso

    assert _senha_para_acesso("senha-configurada", "127.0.0.1", False) == ""
    assert _senha_para_acesso("senha-configurada", "localhost", False) == ""
    assert _senha_para_acesso("senha-configurada", "::1", False) == ""
    assert _senha_para_acesso("senha-configurada", "0.0.0.0", False) == "senha-configurada"
    assert _senha_para_acesso("senha-configurada", "127.0.0.1", True) == "senha-configurada"
