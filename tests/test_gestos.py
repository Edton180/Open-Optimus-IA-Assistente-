"""Gestos: o filtro que decide quando um gesto vale (roda no Node, igual ao navegador)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ESTATICOS = Path(__file__).resolve().parents[1] / "optimus" / "web" / "static"

_ROTEIRO = r"""
const { novoFiltroGestos } = require(process.argv[1]);
const f = novoFiltroGestos({ estavelMs: 600, pausaMs: 1500, confianca: 0.7 });
const saida = [];
const passo = (nome, score, t) => saida.push([t, f(nome, score, t)]);
// 👍 segurado: só vale depois de 600 ms, e uma vez só enquanto a mão fica parada
for (let t = 0; t <= 2000; t += 100) passo("Thumb_Up", 0.9, t);
// a câmera perde a mão num quadro só: NÃO repete o gesto
passo("None", 0.9, 2100); for (let t = 2200; t <= 2900; t += 100) passo("Thumb_Up", 0.9, t);
// confiança baixa nunca vale
for (let t = 3000; t <= 4000; t += 100) passo("Open_Palm", 0.4, t);
// depois da pausa, outro gesto vale
for (let t = 4100; t <= 4800; t += 100) passo("Open_Palm", 0.95, t);
// gesto que o Optimus não conhece
for (let t = 5000; t <= 6000; t += 100) passo("Gesto_X", 0.99, t);
// mão saiu de verdade e a pausa passou: o mesmo 👍 vale de novo
for (let t = 6100; t <= 6800; t += 100) passo("Thumb_Up", 0.9, t);
console.log(JSON.stringify(saida.filter(([, g]) => g)));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
def test_filtro_de_gestos():
    r = subprocess.run(["node", "-e", _ROTEIRO, str(ESTATICOS / "gestos.js")],
                       capture_output=True, text=True, timeout=30, check=True)
    disparos = json.loads(r.stdout)
    # um quadro "vazio" no começo da janela não atrapalha (maioria de 75%)
    assert disparos == [[600, "Thumb_Up"], [4600, "Open_Palm"], [6600, "Thumb_Up"]]


_ROTEIRO_PRECISAO = r"""
const { novoFiltroGestos, novoDetectorDeslize } = require(process.argv[1]);
const r = {};
// 1) um quadro errado no meio NÃO zera a contagem (antes zerava e atrasava o gesto)
let f = novoFiltroGestos();
let saida = [];
for (let t = 0; t <= 1000; t += 100) {
  const g = f(t === 300 ? "Thumb_Down" : "Thumb_Up", 0.9, t, { x: 0.5, y: 0.5 });
  if (g) saida.push([t, g]);
}
r.ruido = saida;
// 2) mão andando pela tela com o polegar para cima: NÃO dispara
f = novoFiltroGestos(); saida = [];
for (let t = 0; t <= 1500; t += 100) {
  const g = f("Thumb_Up", 0.9, t, { x: 0.1 + t / 3000, y: 0.5 });
  if (g) saida.push([t, g]);
}
r.andando = saida;
// 3) gestos novos (✊ e 🤟) valem
f = novoFiltroGestos(); saida = [];
for (let t = 0; t <= 700; t += 100) { const g = f("Closed_Fist", 0.9, t); if (g) saida.push(g); }
for (let t = 800; t <= 1400; t += 100) f("None", 0, t);
for (let t = 2600; t <= 3300; t += 100) { const g = f("ILoveYou", 0.9, t); if (g) saida.push(g); }
r.novos = saida;
// 4) bloquear segura os gestos parados (depois de um deslize)
f = novoFiltroGestos(); f.bloquear(1000); saida = [];
for (let t = 0; t <= 1700; t += 100) { const g = f("Open_Palm", 0.9, t); if (g) saida.push([t, g]); }
r.bloqueio = saida;
// 5) deslizes: a imagem é espelhada (pulso para a esquerda da imagem = SUA direita)
const d = novoDetectorDeslize();
const desliza = (x0, y0, x1, y1, t0) => {
  let achou = null;
  for (let i = 0; i < 4; i++) achou = achou || d({ x: x0, y: y0 }, t0 - 400 + i * 100);  // mão parada antes
  for (let i = 0; i <= 4; i++) {
    const g = d({ x: x0 + (x1 - x0) * i / 4, y: y0 + (y1 - y0) * i / 4 }, t0 + i * 100);
    achou = achou || g;
  }
  d(null, t0 + 500);
  return achou;
};
r.deslizes = [desliza(0.8, 0.5, 0.3, 0.52, 0), desliza(0.3, 0.5, 0.8, 0.5, 2000),
              desliza(0.5, 0.8, 0.5, 0.3, 4000), desliza(0.5, 0.3, 0.5, 0.8, 6000),
              desliza(0.5, 0.5, 0.55, 0.52, 8000),  // mexida pequena: nada
              desliza(0.3, 0.3, 0.7, 0.7, 10000)];  // diagonal: nada
// levantar a mão de baixo para cima logo que ela aparece: NÃO é deslize
const d2 = novoDetectorDeslize(); let entrou = null;
for (let i = 0; i <= 4; i++) entrou = entrou || d2({ x: 0.5, y: 0.95 - i * 0.12 }, 20000 + i * 60);
r.entrando = entrou;
console.log(JSON.stringify(r));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
def test_gestos_mais_precisos_e_novos():
    r = subprocess.run(["node", "-e", _ROTEIRO_PRECISAO, str(ESTATICOS / "gestos.js")],
                       capture_output=True, text=True, timeout=30, check=True)
    d = json.loads(r.stdout)
    assert d["ruido"] == [[600, "Thumb_Up"]]
    assert d["andando"] == []
    assert d["novos"] == ["Closed_Fist", "ILoveYou"]
    assert d["bloqueio"] == [[1600, "Open_Palm"]]
    assert d["deslizes"] == ["Swipe_Right", "Swipe_Left", "Swipe_Up", "Swipe_Down", None, None]
    assert d["entrando"] is None


def test_app_trata_os_gestos_novos():
    js = (ESTATICOS / "app.js").read_text(encoding="utf-8")
    for gesto in ("Closed_Fist", "ILoveYou", "Swipe_Left", "Swipe_Right", "Swipe_Up",
                  "Swipe_Down"):
        assert f'"{gesto}"' in js


def test_pagina_carrega_os_gestos():
    html = (ESTATICOS / "index.html").read_text(encoding="utf-8")
    assert '<script src="/gestos.js"></script>' in html
    assert html.index("/gestos.js") < html.index("/app.js")  # app.js usa o Gestos
    assert 'id="botao-gestos"' in html and 'id="gestos-video"' in html
    js = (ESTATICOS / "gestos.js").read_text(encoding="utf-8")
    assert 'const VERSAO = "0.10.14"' in js  # versão fixa, nunca "latest"
    assert "tasks-vision@${VERSAO}" in js
