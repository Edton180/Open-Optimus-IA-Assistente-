"""Fase 2: utilitários do dia a dia, desfazer organização, desligar com atraso, modo só executar."""

import copy
import datetime as dt
import string

from optimus import config as cfg
from optimus.roteador import selecionar_ferramentas
from optimus.tools import controle, sistema
from optimus.tools import utilitarios as u
from optimus.tools.base import Contexto, Ferramenta


def _ctx(tmp_path, config=None):
    return Contexto(config=config, pasta_trabalho=tmp_path)


# ------------------------------------------------------------------ senha / sorteio
def test_senha_forte_com_todos_os_grupos(tmp_path):
    r = u.gerar_senha(_ctx(tmp_path), tamanho=24)
    s = r["senha"]
    assert len(s) == 24
    assert any(c in string.ascii_lowercase for c in s)
    assert any(c in string.ascii_uppercase for c in s)
    assert any(c in string.digits for c in s)
    assert any(c in "!@#$%&*-_=+?" for c in s)
    sem = u.gerar_senha(_ctx(tmp_path), tamanho=3, simbolos=False)["senha"]
    assert len(sem) == 6 and sem.isalnum()  # mínimo de 6


def test_sortear(tmp_path):
    c = _ctx(tmp_path)
    assert u.sortear(c, "moeda")["resultado"] in ("cara", "coroa")
    assert 1 <= int(u.sortear(c, "dado")["resultado"]) <= 6
    n = u.sortear(c, "numero", minimo=10, maximo=12)["resultado"]
    assert 10 <= int(n) <= 12
    assert u.sortear(c, "lista", itens="ana, bia, caio")["resultado"] in ("ana", "bia", "caio")


# ------------------------------------------------------------------ datas
def test_pascoa_e_carnaval():
    assert u._pascoa(2027) == dt.date(2027, 3, 28)
    hoje = dt.date(2026, 11, 22)
    assert u.interpretar_data("Páscoa", hoje) == dt.date(2027, 3, 28)
    assert u.interpretar_data("carnaval", hoje) == dt.date(2027, 2, 9)


def test_dias_ate(tmp_path):
    hoje = dt.date(2026, 11, 22)
    r = u.dias_ate(_ctx(tmp_path), "Natal", hoje=hoje)
    assert r["dias"] == 33 and r["data"] == "25/12/2026"
    assert u.dias_ate(_ctx(tmp_path), "22/11", hoje=hoje)["mensagem"].startswith("É hoje")
    assert u.dias_ate(_ctx(tmp_path), "01/01/2026", hoje=hoje)["dias"] < 0
    assert "erro" in u.dias_ate(_ctx(tmp_path), "quando der", hoje=hoje)


# ------------------------------------------------------------------ câmbio
class _Resp:
    def __init__(self, dados):
        self.dados = dados

    def raise_for_status(self):
        pass

    def json(self):
        return self.dados


class _Cliente:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return _Resp({"USDBRL": {"bid": "5.4321", "pctChange": "0.1",
                                 "create_date": "2026-11-22 10:00:00"}})


def test_cotacao_com_conversao(tmp_path):
    cli = _Cliente()
    r = u.cotacao(_ctx(tmp_path), "dólar", "real", valor=10, cliente=cli)
    assert cli.urls[0].endswith("/USD-BRL")
    assert r["cotacao"] == 5.4321 and r["convertido"] == 54.32
    assert "1 USD = 5,43 BRL" in r["mensagem"]
    assert "erro" in u.cotacao(_ctx(tmp_path), "real", "real", cliente=cli)


def test_cotacao_sem_rede_nao_quebra(tmp_path):
    class Quebrado:
        def get(self, url):
            raise OSError("sem internet")

    assert "erro" in u.cotacao(_ctx(tmp_path), "euro", cliente=Quebrado())


# ------------------------------------------------------------------ textos rápidos e notas
def test_textos_rapidos(tmp_path, monkeypatch):
    copiado = {}
    monkeypatch.setattr(u, "_copiar", lambda t: copiado.setdefault("t", t) is not None)
    c = _ctx(tmp_path)
    u.texto_rapido_salvar(c, "meu Pix", "chave@exemplo.com")
    assert u.textos_rapidos_listar(c)["textos"] == ["pix"]
    assert "Copiei" in u.texto_rapido_copiar(c, "meu pix")["mensagem"]
    assert copiado["t"] == "chave@exemplo.com"
    assert "erro" in u.texto_rapido_copiar(c, "endereço")
    u.texto_rapido_apagar(c, "pix")
    assert u.textos_rapidos_listar(c)["textos"] == []


def test_notas(tmp_path):
    c = _ctx(tmp_path)
    u.nota_criar(c, "comprar café")
    u.nota_criar(c, "ligar pro João")
    u.nota_criar(c, "ideia de vídeo", titulo="Ideias")
    notas = {n["titulo"]: n["itens"] for n in u.notas_listar(c)["notas"]}
    assert notas == {"Anotações": 2, "Ideias": 1}
    assert "comprar café" in u.nota_ler(c)["conteudo"]
    achados = u.notas_buscar(c, "CAFE")["achados"]
    assert len(achados) == 1 and "café" in achados[0]["linha"]
    u.nota_apagar(c, "Ideias")
    assert "erro" in u.nota_ler(c, "Ideias")


# ------------------------------------------------------------------ desfazer organização
def test_organizar_e_desfazer(tmp_path):
    pasta = tmp_path / "Downloads"
    pasta.mkdir()
    for nome in ("foto.jpg", "nota.pdf", "musica.mp3"):
        (pasta / nome).write_text("x")
    c = _ctx(tmp_path)
    controle.organizar_pasta(c, str(pasta), simular=False)
    assert not (pasta / "foto.jpg").exists()
    r = controle.organizar_desfazer(c)
    assert r["voltaram"] == 3
    assert sorted(p.name for p in pasta.iterdir()) == ["foto.jpg", "musica.mp3", "nota.pdf"]
    assert "erro" in controle.organizar_desfazer(c)  # nada mais a desfazer


def test_desfazer_nao_sobrescreve(tmp_path):
    pasta = tmp_path / "p"
    pasta.mkdir()
    (pasta / "a.txt").write_text("velho")
    c = _ctx(tmp_path)
    controle.organizar_pasta(c, str(pasta), simular=False)
    (pasta / "a.txt").write_text("novo")  # o usuário criou outro com o mesmo nome
    controle.organizar_desfazer(c)
    assert (pasta / "a.txt").read_text() == "novo"
    assert (pasta / "a (1).txt").read_text() == "velho"


# ------------------------------------------------------------------ energia com atraso
def test_desligar_em_minutos_usa_comando_nativo(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(sistema.subprocess, "Popen", lambda cmd, **k: chamadas.append(cmd))
    monkeypatch.setattr(sistema, "sistema", lambda: "windows")
    r = sistema.energia(_ctx(tmp_path), "desligar", minutos=30)
    assert chamadas == ["shutdown /s /t 1800"] and "hora" in r
    monkeypatch.setattr(sistema, "sistema", lambda: "linux")
    sistema.energia(_ctx(tmp_path), "reiniciar", minutos=5)
    assert chamadas[-1] == "shutdown -r +5"


def test_suspender_em_minutos_usa_timer_e_cancela(tmp_path, monkeypatch):
    monkeypatch.setattr(sistema.subprocess, "Popen", lambda cmd, **k: None)
    monkeypatch.setattr(sistema, "sistema", lambda: "linux")
    sistema.energia(_ctx(tmp_path), "suspender", minutos=10)
    timer = sistema._AGENDADO["timer"]
    assert timer.is_alive()
    sistema.energia(_ctx(tmp_path), "cancelar")
    timer.join(1)
    assert not timer.is_alive() and "timer" not in sistema._AGENDADO


def test_risco_da_energia_mostra_minutos():
    from optimus.tools.base import registradas

    av = registradas()["energia"].avaliar({"acao": "desligar", "minutos": 30}, None)
    assert "30 min" in av.motivo


# ------------------------------------------------------------------ modo só executar
def test_modo_so_executar_grava_na_config(tmp_path):
    c = cfg.Config(copy.deepcopy(cfg.PADRAO))
    c.caminho = tmp_path / "config.toml"
    u.modo_so_executar(_ctx(tmp_path, c), ligar=True)
    assert c.get("voz", "so_executar") is True
    assert cfg.carregar(c.caminho).get("voz", "so_executar") is True
    u.modo_so_executar(_ctx(tmp_path, c), ligar=False)
    assert c.get("voz", "so_executar") is False


# ------------------------------------------------------------------ roteador
NOMES = ["gerar_senha", "sortear", "dias_ate", "cotacao", "texto_rapido_copiar",
         "texto_rapido_salvar", "nota_criar", "modo_so_executar", "organizar_desfazer",
         "energia"]
DISPONIVEIS = {n: Ferramenta(n, "x", {}, None) for n in NOMES}


def _sel(t):
    return set(selecionar_ferramentas(t, DISPONIVEIS))


def test_roteador_fase2():
    casos = {
        "gera uma senha de 20": "gerar_senha",
        "cara ou coroa": "sortear",
        "quantos dias faltam pro natal?": "dias_ate",
        "quanto está o dólar?": "cotacao",
        "copia meu pix": "texto_rapido_copiar",
        "anota que preciso comprar café": "nota_criar",
        "modo só executar": "modo_so_executar",
        "desfaz a organização da pasta": "organizar_desfazer",
        "desliga o pc em 30 minutos": "energia",
    }
    for pedido, nome in casos.items():
        assert nome in _sel(pedido), pedido
