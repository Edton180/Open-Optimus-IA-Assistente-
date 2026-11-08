from optimus.hardware import Hardware, Placa, escolher_perfil


def pc(ram, livre=None, placa=None, nucleos=4):
    return Hardware("Linux", "6", "x86_64", "CPU", nucleos, nucleos * 2, ram,
                    livre if livre is not None else ram * 0.8, placa)


def test_pc_fraco_usa_modelo_minusculo():
    perfil = escolher_perfil(pc(4))
    assert perfil.nome == "mínimo"
    assert perfil.modelo == "qwen3.5:0.8b"
    assert perfil.contexto == 2048
    assert perfil.threads == 3  # deixa um núcleo livre


def test_notebook_8gb():
    assert escolher_perfil(pc(8)).nome == "leve"


def test_placa_de_video_manda_na_escolha():
    perfil = escolher_perfil(pc(16, placa=Placa("nvidia", "RTX 4090", 24)))
    assert perfil.usa_gpu and perfil.nome == "ultra"
    assert perfil.modelo == "qwen3.5:27b"
    assert perfil.modelo_rapido == "qwen3.5:2b"


def test_muita_ram_sem_gpu_usa_moe():
    perfil = escolher_perfil(pc(64, nucleos=16))
    assert perfil.modelo == "qwen3.5:35b-a3b"
    assert not perfil.usa_gpu


def test_ram_quase_cheia_reduz_o_modelo():
    folgado = escolher_perfil(pc(16, livre=12))
    apertado = escolher_perfil(pc(16, livre=2))
    assert apertado.memoria_util_gb < folgado.memoria_util_gb
    assert apertado.nome in ("mínimo", "leve")
