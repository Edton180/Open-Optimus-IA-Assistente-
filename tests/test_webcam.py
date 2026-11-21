"""Câmeras por cabo (USB): listagem por sistema, foto pelo ffmpeg e integração na Casa."""

import shutil

import pytest

from optimus import webcam
from optimus.config import Config
from optimus.roteador import selecionar_ferramentas
from optimus.safety import CRITICO, LIVRE, precisa_confirmar
from optimus.tools import casa, ferramentas_ativas
from optimus.tools.base import Contexto


@pytest.fixture(autouse=True)
def _sem_cache():
    webcam._CACHE.update(quando=0.0, lista=[])
    yield
    webcam._CACHE.update(quando=0.0, lista=[])


def test_entrada_do_ffmpeg_por_sistema():
    assert webcam.entrada_ffmpeg(1, "linux") == ["-f", "v4l2", "-i", "/dev/video1"]
    assert webcam.entrada_ffmpeg(0, "macos")[-1] == "0:none"
    assert webcam.entrada_ffmpeg(0, "windows", "HD Webcam") == ["-f", "dshow", "-i",
                                                                "video=HD Webcam"]


def test_lista_de_dispositivos_windows_e_mac():
    novo = ('[dshow @ 01] "Integrated Camera" (video)\n'
            '[dshow @ 01]   Alternative name "@device_pnp_\\\\?\\usb"\n'
            '[dshow @ 01] "Microfone (Realtek)" (audio)\n'
            '[dshow @ 01] "USB2.0 HD UVC WebCam" (video)\n')
    assert webcam.ler_dispositivos(novo, "windows") == ["Integrated Camera",
                                                        "USB2.0 HD UVC WebCam"]
    antigo = ('[dshow @ 02] DirectShow video devices (some may be both video and audio)\n'
              '[dshow @ 02]  "Logitech C920"\n'
              '[dshow @ 02]     Alternative name "@device_pnp_xyz"\n'
              '[dshow @ 02] DirectShow audio devices\n'
              '[dshow @ 02]  "Microfone"\n')
    assert webcam.ler_dispositivos(antigo, "windows") == ["Logitech C920"]
    mac = ("[AVFoundation indev @ 0x1] AVFoundation video devices:\n"
           "[AVFoundation indev @ 0x1] [0] FaceTime HD Camera\n"
           "[AVFoundation indev @ 0x1] [1] Capture screen 0\n"
           "[AVFoundation indev @ 0x1] AVFoundation audio devices:\n"
           "[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone\n")
    assert webcam.ler_dispositivos(mac, "macos") == ["FaceTime HD Camera"]


def test_linux_ignora_o_dispositivo_de_metadados(tmp_path):
    for numero, indice, nome in ((0, "0", "HD Webcam"), (1, "1", "HD Webcam"),
                                 (2, "0", "USB Camera")):
        pasta = tmp_path / f"video{numero}"
        pasta.mkdir()
        (pasta / "index").write_text(indice)
        (pasta / "name").write_text(nome)
    assert webcam._linux(tmp_path) == [{"indice": 0, "nome": "HD Webcam"},
                                       {"indice": 2, "nome": "USB Camera"}]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_foto_de_verdade_pelo_ffmpeg(monkeypatch):
    # Fonte de vídeo sintética no lugar da webcam: testa o caminho real do ffmpeg.
    monkeypatch.setattr(webcam, "_foto_opencv", lambda _i: None)
    monkeypatch.setattr(webcam, "entrada_ffmpeg",
                        lambda *_a: ["-f", "lavfi", "-i", "testsrc=size=320x240:rate=30"])
    imagem = webcam.foto(0, "linux")
    assert imagem[:2] == b"\xff\xd8" and len(imagem) > 1000  # um JPEG de verdade


def test_webcam_quebrada_vira_erro_claro(monkeypatch):
    monkeypatch.setattr(webcam, "_foto_opencv", lambda _i: None)
    monkeypatch.setattr(webcam.shutil, "which", lambda _n: None)
    with pytest.raises(RuntimeError, match="opencv-python"):
        webcam.foto(0, "linux")


def test_webcams_aparecem_na_casa(monkeypatch):
    monkeypatch.setattr(webcam, "listar", lambda *a, **k: [{"indice": 0, "nome": "HD Webcam"}])
    ids = [c["id"] for c in casa.cameras_configuradas(Config())]
    assert "usb:0" in ids
    desligada = Config()
    desligada.definir("casa", "webcams", False)
    assert "usb:0" not in [c["id"] for c in casa.cameras_configuradas(desligada)]


def test_foto_da_webcam_pede_confirmacao_em_todos_os_modos():
    ctx = Contexto(config=Config())
    for camera in ("usb:0", "webcam", "USB:1"):
        nivel = casa._risco_foto({"camera": camera}, ctx).nivel
        assert nivel == CRITICO
        assert all(precisa_confirmar(nivel, modo) for modo in ("seguro", "equilibrado", "autonomo"))
    assert casa._risco_foto({"camera": "http://cam/snap.jpg"}, ctx).nivel == LIVRE


def test_pedido_de_webcam_chega_na_ferramenta(monkeypatch):
    monkeypatch.setattr(webcam, "listar", lambda *a, **k: [])
    ctx = Contexto(config=Config())
    assert casa.camera_foto(ctx, "webcam") == {"erro": "Não achei nenhuma webcam ligada "
                                                        "neste computador."}
    assert "erro" in casa.camera_foto(ctx, "usb:x")
    escolhidas = selecionar_ferramentas("tira uma foto pela webcam", ferramentas_ativas(Config()),
                                        pequeno=True)
    assert "camera_foto" in escolhidas
