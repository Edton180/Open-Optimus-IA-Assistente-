from pathlib import Path

import pytest

from optimus import kiwix


class ProcessoFalso:
    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.returncode = None
        self.terminado = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminado = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def _preparar(tmp_path, monkeypatch):
    pasta = tmp_path / "biblioteca_zim"
    pasta.mkdir()
    (pasta / "wikipedia_pt.zim").write_bytes(b"ZIM")
    monkeypatch.setattr(kiwix.zim, "pasta_biblioteca", lambda: pasta)
    monkeypatch.setattr(kiwix, "_executavel", lambda: "/usr/bin/kiwix-serve")
    monkeypatch.setattr(kiwix.time, "sleep", lambda _: None)
    monkeypatch.setattr(kiwix, "_processo", None)
    monkeypatch.setattr(kiwix, "_arquivo_ativo", None)
    monkeypatch.setattr(kiwix, "_porta_disponivel", lambda: kiwix.PORT)
    return pasta


def test_inicia_kiwix_local_sem_shell(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    criados = []

    def criar(args, **kwargs):
        p = ProcessoFalso(args, **kwargs)
        criados.append(p)
        return p

    monkeypatch.setattr(kiwix.subprocess, "Popen", criar)

    dados = kiwix.iniciar("wikipedia_pt.zim")

    assert dados["executando"] is True
    assert dados["arquivo"] == "wikipedia_pt.zim"
    assert dados["url"] == "http://127.0.0.1:8767/"
    assert criados[0].kwargs["shell"] is False
    assert "--address=127.0.0.1" in criados[0].args
    assert "--port=8767" in criados[0].args
    assert Path(criados[0].args[-1]).name == "wikipedia_pt.zim"
    assert criados[0].kwargs["stdin"] == kiwix.subprocess.DEVNULL


def test_nao_permite_caminho_externo_ou_travessia(tmp_path, monkeypatch):
    pasta = _preparar(tmp_path, monkeypatch)
    externo = tmp_path / "fora.zim"
    externo.write_bytes(b"fora")
    with pytest.raises(ValueError):
        kiwix.iniciar("../fora.zim")
    with pytest.raises(ValueError):
        kiwix.iniciar(str(externo))
    try:
        (pasta / "atalho.zim").symlink_to(externo)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValueError):
        kiwix.iniciar("atalho.zim")


def test_nao_inicia_sem_kiwix(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(kiwix, "_executavel", lambda: None)
    with pytest.raises(FileNotFoundError):
        kiwix.iniciar("wikipedia_pt.zim")


def test_para_somente_processo_gerenciado(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    processos = []

    def criar(args, **kwargs):
        p = ProcessoFalso(args, **kwargs)
        processos.append(p)
        return p

    monkeypatch.setattr(kiwix.subprocess, "Popen", criar)
    kiwix.iniciar("wikipedia_pt.zim")
    dados = kiwix.parar()

    assert processos[0].terminado is True
    assert dados["executando"] is False
    assert dados["url"] is None


def test_busca_kiwix_parseia_resultados_com_citacao(monkeypatch):
    xml = b"""<?xml version="1.0"?>
    <rss><channel><item><title>Primeiros socorros</title>
    <link>/content/wikipedia_pt/Primeiros_socorros</link>
    <description>Procedimentos iniciais de atendimento.</description></item></channel></rss>"""
    monkeypatch.setattr(kiwix.zim, "listar_zim", lambda: {
        "arquivos": [{"nome": "wikipedia_pt.zim"}]
    })
    monkeypatch.setattr(kiwix, "_processo", None)
    monkeypatch.setattr(kiwix, "_arquivo_ativo", None)
    monkeypatch.setattr(kiwix, "iniciar", lambda nome: {
        "executando": True, "arquivo": nome
    })
    monkeypatch.setattr(kiwix, "parar", lambda: {"executando": False})

    class Resposta:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limite): return xml

    monkeypatch.setattr(kiwix.urllib.request, "urlopen", lambda *a, **k: Resposta())
    dados = kiwix.buscar("primeiros socorros")

    assert dados["total"] == 1
    assert dados["resultados"][0]["titulo"] == "Primeiros socorros"
    assert dados["resultados"][0]["arquivo_zim"] == "wikipedia_pt.zim"
    assert "127.0.0.1" in dados["resultados"][0]["url"]
    assert dados["resultados"][0]["citacao"] == "wikipedia_pt.zim · Primeiros socorros"


def test_busca_nao_interrompe_leitor_gerenciado_de_outro_zim(monkeypatch):
    monkeypatch.setattr(kiwix.zim, "listar_zim", lambda: {
        "arquivos": [{"nome": "outro.zim"}]
    })
    monkeypatch.setattr(kiwix, "_processo", ProcessoFalso([], shell=False))
    monkeypatch.setattr(kiwix, "_arquivo_ativo", "aberto.zim")
    chamados = []
    monkeypatch.setattr(kiwix, "parar", lambda: chamados.append("parar"))
    dados = kiwix.buscar("consulta")

    assert dados["total"] == 0
    assert dados["erros"]
    assert chamados == []


def test_busca_rejeita_consulta_curta(monkeypatch):
    with pytest.raises(ValueError):
        kiwix.buscar("x")


def test_instalador_usa_pacote_local_sem_path_global(tmp_path, monkeypatch):
    import tarfile
    import zipfile
    from optimus import kiwix_manager

    raiz = tmp_path / "kiwix-tools"
    monkeypatch.setattr(kiwix_manager, "diretorio", lambda: raiz)
    sistema = kiwix_manager.platform.system()
    maquina = kiwix_manager.platform.machine()
    monkeypatch.setattr(kiwix_manager.platform, "system", lambda: sistema)
    monkeypatch.setattr(kiwix_manager.platform, "machine", lambda: maquina)
    windows = sistema.lower() == "windows"
    nome_binario = "kiwix-serve.exe" if windows else "kiwix-serve"

    def baixar(url, destino):
        if windows:
            with zipfile.ZipFile(destino, "w") as pacote:
                pacote.writestr("kiwix-tools/" + nome_binario, b"fake-exe")
        else:
            temporario = tmp_path / nome_binario
            temporario.write_bytes(b"fake-exe")
            with tarfile.open(destino, "w:gz") as pacote:
                pacote.add(temporario, arcname="kiwix-tools/" + nome_binario)

    monkeypatch.setattr(kiwix_manager, "_baixar", baixar)
    dados = kiwix_manager.instalar()

    assert dados["instalado"] is True
    assert dados["gerenciado"] is True
    assert Path(dados["executavel"]).is_file()
    assert str(raiz) in dados["executavel"]


def test_extracao_rejeita_traversal_zip(tmp_path):
    import zipfile
    from optimus import kiwix_manager

    pacote = tmp_path / "ruim.zip"
    with zipfile.ZipFile(pacote, "w") as z:
        z.writestr("../fora.txt", "conteudo")
    with pytest.raises(RuntimeError):
        kiwix_manager._extrair_zip(pacote, tmp_path / "saida")


def test_normaliza_nome_zim_conforme_kiwix():
    assert kiwix._zim_name("Wikipédia + Saúde 2026.ZIM") == "wikipedia_plus_saude_2026"
