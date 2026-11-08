"""Testes das novidades da v0.2: internet com reservas, modelos por família, casa, câmeras,
início automático, voz e servidor (confirmações, modos, segredos)."""

import json
import urllib.error
import urllib.request

import pytest

from optimus.agent import Agente
from optimus.config import Config
from optimus.hardware import Hardware, Placa, escolher_perfil
from optimus.roteador import roteador_rapido, selecionar_ferramentas
from optimus.tools import ferramentas_ativas
from tests.test_agente import MotorRoteiro
from tests.test_web import _req, _subir

# ------------------------------------------------------------------ internet (sem rede)
DDG = """
<div class="result results_links results_links_deep web-result ">
 <div class="links_main links_deep result__body">
  <h2 class="result__title"><a rel="nofollow" class="result__a"
   href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.bcb.gov.br%2Fcotacoes&amp;rut=x">
   Cotações - <b>Banco Central</b></a></h2>
  <a class="result__snippet" href="x">Cotação do <b>dólar</b> hoje.</a>
 </div>
</div>
"""
BING = """<ol id="b_results"><li class="b_algo"><h2>
<a href="https://g1.globo.com/economia" h="x">Economia | <strong>g1</strong></a></h2>
<div class="b_caption"><p>Notícias de economia &amp; mercado.</p></div></li></ol>"""
RSS = """<rss><channel><item><title><![CDATA[Dólar fecha em queda - Valor]]></title>
<link>https://news.google.com/x</link><pubDate>Sun, 08 Nov 2026 12:00:00 GMT</pubDate>
<source url="https://valor.globo.com">Valor Econômico</source></item></channel></rss>"""


def test_leitores_de_busca_e_rss():
    from optimus.tools.internet import ler_bing_html, ler_duckduckgo_html, ler_rss

    ddg = ler_duckduckgo_html(DDG)
    assert ddg == [{"nome": "Cotações - Banco Central", "link": "https://www.bcb.gov.br/cotacoes",
                    "trecho": "Cotação do dólar hoje."}]
    bing = ler_bing_html(BING)
    assert bing[0]["link"] == "https://g1.globo.com/economia" and "mercado" in bing[0]["trecho"]
    noticia = ler_rss(RSS)[0]
    assert noticia["nome"] == "Dólar fecha em queda - Valor"
    assert noticia["fonte"] == "Valor Econômico" and noticia["link"].startswith("https://")


def test_pesquisa_usa_o_proximo_buscador(monkeypatch):
    from optimus.tools import internet

    def falha(consulta, limite):
        raise OSError("sem rede")

    monkeypatch.setattr(internet, "BUSCADORES", [
        ("A", falha), ("B", lambda c, n: []), ("C", lambda c, n: [{"nome": "ok", "link": "l"}])])
    from optimus.tools.base import Contexto

    resultado = internet.pesquisar_web(Contexto(config=Config()), "teste")
    assert resultado["buscador"] == "C" and resultado["itens"][0]["nome"] == "ok"


# ------------------------------------------------------------------ roteador e modos
def test_gerar_imagem_vai_direto():
    assert roteador_rapido("Gere uma imagem de um gato astronauta") == (
        "gerar_imagem", {"descricao": "um gato astronauta"})
    assert roteador_rapido("Optimus, crie uma ilustração: castelo à noite")[1] == {
        "descricao": "castelo à noite"}
    assert roteador_rapido("gere um relatório de vendas") is None


def test_modos_da_interface():
    from optimus.web.server import _aplicar_modo

    assert _aplicar_modo("dólar hoje", "web") == "Pesquise na internet sobre dólar hoje"
    assert _aplicar_modo("um gato", "imagem") == "Gere uma imagem de um gato"
    assert _aplicar_modo("oi", "") == "oi"


def test_bluetooth_e_camera_chegam_ao_modelo_pequeno():
    config = Config()
    config.definir("casa", "url", "http://ha:8123")
    config.definir("casa", "token", "t")
    todas = ferramentas_ativas(config)
    bt = selecionar_ferramentas("conecte o fone bluetooth", todas, pequeno=True)
    assert "bluetooth_conectar" in bt and len(bt) <= 6
    cam = selecionar_ferramentas("mostre a câmera do portão", todas, pequeno=True)
    assert "cameras_listar" in cam and "camera_foto" in cam


def test_pensar_a_fundo_por_pedido(tmp_path):
    agente = Agente(config=Config(), motor=MotorRoteiro([]))
    assert agente.opcoes()["pensar"] is False
    agente.pensar = True
    assert agente.opcoes()["pensar"] is True


# ------------------------------------------------------------------ modelos por hardware
def _hw(ram=16.0, vram=0.0):
    placa = Placa("nvidia", "RTX", vram) if vram else None
    return Hardware("Linux", "6", "x86_64", "cpu", 4, 8, ram, ram - 2, placa,
                    [placa] if placa else [])


def test_melhor_modelo_de_cada_familia():
    from optimus import modelos

    fraco = {f["familia"]: f for f in modelos.melhores_por_familia(_hw(ram=8))}
    assert fraco["Gemma (Google)"]["recomendado"]["nome"] == "gemma3:4b"
    assert fraco["gpt-oss (OpenAI)"]["recomendado"] is None
    forte = {f["familia"]: f for f in modelos.melhores_por_familia(_hw(ram=32, vram=24))}
    assert forte["gpt-oss (OpenAI)"]["recomendado"]["nome"] == "gpt-oss:20b"
    assert forte["DeepSeek"]["recomendado"]["nome"] == "deepseek-r1:32b"


def test_aviso_quando_o_hardware_melhora(tmp_path):
    from optimus import modelos

    config = Config()
    config.caminho = tmp_path / "config.toml"
    antigo = _hw(ram=8)
    assert modelos.verificar_upgrade(config, antigo, escolher_perfil(antigo)) is None
    assert config.get("motor", "hardware_assinatura") == modelos.assinatura(antigo)
    config.definir("motor", "modelo", "qwen3.5:2b")
    novo = _hw(ram=32, vram=12)
    aviso = modelos.verificar_upgrade(config, novo, escolher_perfil(novo))
    assert aviso and aviso["modelo"] == escolher_perfil(novo).modelo
    assert "Quer trocar" in aviso["texto"]
    modelos.aceitar_upgrade(config, novo, aviso["modelo"])
    assert config.get("motor", "modelo") == aviso["modelo"]
    assert modelos.verificar_upgrade(config, novo, escolher_perfil(novo)) is None


# ------------------------------------------------------------------ casa e câmeras
def test_sugestoes_da_casa():
    from optimus.tools.casa import sugestoes_da_casa

    estados = [
        {"entity_id": "sensor.sala_temp", "state": "31",
         "attributes": {"device_class": "temperature", "friendly_name": "Sala"}},
        {"entity_id": "climate.ar_sala", "state": "off", "attributes": {}},
        {"entity_id": "binary_sensor.porta", "state": "on",
         "attributes": {"device_class": "door", "friendly_name": "Porta da frente"}},
    ]
    sugestoes = " ".join(sugestoes_da_casa(estados))
    assert "31°C" in sugestoes and "ligue o ar" in sugestoes and "Porta da frente" in sugestoes


def test_riscos_da_casa():
    from optimus.safety import CRITICO, MODERADO
    from optimus.tools.casa import _risco_falar, _risco_varios

    assert _risco_falar({"texto": "destranque a porta"}, None).nivel == CRITICO
    assert _risco_falar({"texto": "apague a luz da sala"}, None).nivel == MODERADO
    passos = {"comandos": [{"id": "light.sala", "acao": "desligar"},
                           {"id": "lock.porta", "acao": "destrancar"}]}
    assert _risco_varios(passos, None).nivel == CRITICO


def test_cameras_ip_nao_expoem_a_senha():
    from optimus.tools.casa import cameras_configuradas, imagem_da_camera

    config = Config()
    config.dados["cameras"] = [{"nome": "Portão", "url": "rtsp://adm:segredo@10.0.0.9/s"}]
    assert cameras_configuradas(config) == [{"nome": "Portão", "id": "ip:0"}]
    with pytest.raises(RuntimeError):
        imagem_da_camera(config, "ip:7")


def test_bluetooth_valida_endereco():
    from optimus.tools.base import Contexto
    from optimus.tools.casa import bluetooth_conectar

    assert "inválido" in bluetooth_conectar(Contexto(config=Config()), "fone")["erro"]


# ------------------------------------------------------------------ início automático
def test_arquivos_de_inicio_automatico():
    from optimus import startup

    comando = startup.comando_optimus(abrir_navegador=False)
    assert comando[-2:] == ["gui", "--sem-navegador"]
    unidade = startup.texto_unidade_systemd(comando)
    assert "ExecStart=" in unidade and "WantedBy=default.target" in unidade
    assert "termux-wake-lock" in startup.texto_script_termux(comando)


# ------------------------------------------------------------------ voz e controle
def test_vozes_por_apelido_e_efeitos():
    np = pytest.importorskip("numpy")
    from optimus.voice import tts

    assert tts.buscar_voz("Valquíria").id == "valkyrie"
    assert tts.buscar_voz("feminina").id == "valkyrie"
    som = np.sin(np.linspace(0, 200, 24000)).astype("float32")
    for efeito in ("cyber", "sussurro"):
        saida = tts.aplicar_efeito(som, 24000, efeito)
        assert len(saida) >= len(som) * 0.9 and float(np.abs(saida).max()) <= 1.0


def test_wake_on_lan_e_riscos_de_git_docker():
    from optimus.safety import CRITICO, LIVRE
    from optimus.tools.codigo import risco_docker, risco_git
    from optimus.tools.controle import pacote_wol

    pacote = pacote_wol("AA:BB:CC:DD:EE:FF")
    assert len(pacote) == 102 and pacote[:6] == b"\xff" * 6
    assert risco_git("status") == LIVRE and risco_git("push --force") == CRITICO
    assert risco_docker("ps") == LIVRE and risco_docker("system prune -a") == CRITICO


# ------------------------------------------------------------------ servidor
def test_servidor_confirmacao_segredos_e_cameras():
    from optimus.web import server

    httpd, base = _subir()
    try:
        tarefa = server.Tarefa()
        server.Manipulador.estado.tarefas[tarefa.id] = tarefa
        with pytest.raises(urllib.error.HTTPError) as erro:
            _req(base + "/api/confirmar", {"tarefa": tarefa.id, "aprovar": True})
        assert erro.value.code == 409  # nada pendente: o botão não finge que funcionou
        with pytest.raises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(base + "/api/camera?id=http://169.254.169.254/")
        assert erro.value.code == 404  # não vira proxy para endereços quaisquer
        catalogo = _req(base + "/api/modelos/catalogo")
        assert catalogo["familias"] and catalogo["memoria_util_gb"] > 0
        mascarado = server._mascarar_config({"cameras": [{"url": "rtsp://a:segredo@x/1"}],
                                             "voz": {"elevenlabs_chave": "sk-1"}})
        assert "segredo" not in json.dumps(mascarado) and "sk-1" not in json.dumps(mascarado)
    finally:
        httpd.shutdown()


def test_caminho_do_windows_nao_muda_a_intencao():
    # "AppData" no caminho fazia o pedido parecer de programação e cortava o "apagar".
    todas = ferramentas_ativas(Config())
    pedido = r"apague C:\Users\runneradmin\AppData\Local\Temp\pytest-0\lixo.txt"
    assert "apagar" in selecionar_ferramentas(pedido, todas, pequeno=True)
    assert "apagar" in selecionar_ferramentas("apague ~/projeto/app/x.txt", todas, pequeno=True)
    assert "pesquisar_web" in selecionar_ferramentas("leia https://site.com/x", todas, pequeno=True)
