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
// gesto que o Optimus não usa
for (let t = 5000; t <= 6000; t += 100) passo("ILoveYou", 0.99, t);
// mão saiu de verdade e a pausa passou: o mesmo 👍 vale de novo
for (let t = 6100; t <= 6800; t += 100) passo("Thumb_Up", 0.9, t);
console.log(JSON.stringify(saida.filter(([, g]) => g)));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
def test_filtro_de_gestos():
    r = subprocess.run(["node", "-e", _ROTEIRO, str(ESTATICOS / "gestos.js")],
                       capture_output=True, text=True, timeout=30, check=True)
    disparos = json.loads(r.stdout)
    assert disparos == [[600, "Thumb_Up"], [4700, "Open_Palm"], [6700, "Thumb_Up"]]


def test_pagina_carrega_os_gestos():
    html = (ESTATICOS / "index.html").read_text(encoding="utf-8")
    assert '<script src="/gestos.js"></script>' in html
    assert html.index("/gestos.js") < html.index("/app.js")  # app.js usa o Gestos
    assert 'id="botao-gestos"' in html and 'id="gestos-video"' in html
    js = (ESTATICOS / "gestos.js").read_text(encoding="utf-8")
    assert 'const VERSAO = "0.10.14"' in js  # versão fixa, nunca "latest"
    assert "tasks-vision@${VERSAO}" in js
