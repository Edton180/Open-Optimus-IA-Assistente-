"""Testes isolados do gerenciador Cloudflare Tunnel."""
from optimus.network import cloudflare_tunnel as tunnel


def test_asset_name_linux_x64(monkeypatch):
    monkeypatch.setattr(tunnel.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tunnel.platform, "machine", lambda: "x86_64")
    assert tunnel._asset_name() == "cloudflared-linux-amd64"


def test_asset_name_android_arm64_usa_binario_linux(monkeypatch):
    monkeypatch.setattr(tunnel.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tunnel.platform, "machine", lambda: "aarch64")
    assert tunnel._asset_name() == "cloudflared-linux-arm64"


def test_arquitetura_desconhecida_e_rejeitada(monkeypatch):
    monkeypatch.setattr(tunnel.platform, "system", lambda: "Plan9")
    monkeypatch.setattr(tunnel.platform, "machine", lambda: "mips")
    try:
        tunnel._asset_name()
    except tunnel.TunnelError as erro:
        assert "não suportada" in str(erro)
    else:
        raise AssertionError("arquitetura desconhecida não pode ser aceita")


def test_senha_fraca_nao_inicia_processo(monkeypatch):
    chamadas = []
    monkeypatch.setattr(tunnel.subprocess, "Popen", lambda *a, **k: chamadas.append(a))
    resposta = tunnel.iniciar(8765, "fraca", instalador=lambda: "/tmp/cloudflared")
    assert resposta["erro"]
    assert not chamadas


def test_instalador_com_erro_e_reportado_sem_excecao():
    resposta = tunnel.iniciar(8765, "senha-forte-para-teste",
                              instalador=lambda: (_ for _ in ()).throw(
                                  tunnel.TunnelError("digest inválido")))
    assert resposta["erro"] == "digest inválido"
    assert resposta["ligado"] is False



def test_estado_nao_exibe_url_antes_da_verificacao_publica(monkeypatch):
    class Processo:
        def poll(self):
            return None

    monkeypatch.setattr(tunnel, "_PROCESS", Processo())
    monkeypatch.setattr(tunnel, "_URL", "https://exemplo.trycloudflare.com")
    monkeypatch.setattr(tunnel, "_VERIFICADO", False)
    estado = tunnel.estado()
    assert estado["ligado"] is False
    assert estado["iniciando"] is True
    assert estado["url"] == ""


def test_estado_so_confirma_depois_de_https_publico_verificado(monkeypatch):
    class Processo:
        def poll(self):
            return None

    monkeypatch.setattr(tunnel, "_PROCESS", Processo())
    monkeypatch.setattr(tunnel, "_URL", "https://exemplo.trycloudflare.com")
    monkeypatch.setattr(tunnel, "_VERIFICADO", True)
    estado = tunnel.estado()
    assert estado["ligado"] is True
    assert estado["iniciando"] is False
    assert estado["url"] == "https://exemplo.trycloudflare.com"
