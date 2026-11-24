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
    assert dados["url"] == "http://127.0.0.1:8766/"
    assert criados[0].kwargs["shell"] is False
    assert "--address=127.0.0.1" in criados[0].args
    assert "--port=8766" in criados[0].args
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
