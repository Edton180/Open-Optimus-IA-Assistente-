"""Tradução de legendas pelo modelo de IA do Optimus, com glossário por projeto.

- Traduz em lotes numerados e confere se cada linha voltou; se faltar alguma, tenta de novo
  sozinha e, em último caso, mantém o original (nunca perde uma legenda).
- O glossário guarda termos que não devem ser traduzidos (nomes, marcas) e traduções fixas
  ("deploy" → "implantação"). Pode ser montado sozinho pela IA a partir do texto.
- Para dublagem, pede frases com tamanho parecido ao original, para a fala caber no tempo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from optimus.config import pasta_base
from optimus.estudio import idiomas
from optimus.estudio.audio import ErroEstudio
from optimus.estudio.legendas import Trecho

Llm = Callable[[list[dict]], str]


# ---------------------------------------------------------------------- glossário
def _arq_glossario(projeto: str) -> Path:
    nome = re.sub(r"[^a-z0-9_-]+", "-", (projeto or "geral").lower()).strip("-") or "geral"
    return pasta_base() / "estudio" / "glossarios" / f"{nome}.json"


def glossario(projeto: str = "geral") -> dict:
    try:
        dados = json.loads(_arq_glossario(projeto).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    return {"manter": list(dados.get("manter") or []),
            "traducoes": dict(dados.get("traducoes") or {})}


def salvar_glossario(projeto: str, manter: list[str] | None = None,
                     traducoes: dict[str, str] | None = None, substituir: bool = False) -> dict:
    atual = {"manter": [], "traducoes": {}} if substituir else glossario(projeto)
    for termo in manter or []:
        if termo.strip() and termo.strip() not in atual["manter"]:
            atual["manter"].append(termo.strip())
    atual["traducoes"].update({k.strip(): v.strip() for k, v in (traducoes or {}).items()
                               if k.strip() and v.strip()})
    arq = _arq_glossario(projeto)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
    return atual


def extrair_termos(texto: str, llm: Llm, limite: int = 40) -> list[str]:
    """Pede à IA os nomes próprios, marcas e termos técnicos que não devem ser traduzidos."""
    resposta = llm([
        {"role": "system", "content": "Você extrai termos de um texto. Responda só com JSON."},
        {"role": "user", "content": "Liste os nomes de pessoas, marcas, produtos, lugares e "
                                    "termos técnicos deste texto que NÃO devem ser traduzidos. "
                                    'Formato: {"termos": ["..."]}\n\n' + texto[:6000]},
    ])
    achado = re.search(r"\{.*\}", resposta or "", re.DOTALL)
    try:
        termos = json.loads(achado.group(0))["termos"] if achado else []
    except (ValueError, KeyError, TypeError):
        termos = []
    return [str(t).strip() for t in termos if str(t).strip() and len(str(t)) < 60][:limite]


def _proteger(texto: str, termos: list[str]) -> tuple[str, dict[str, str]]:
    marcas: dict[str, str] = {}
    for i, termo in enumerate(sorted(termos, key=len, reverse=True)):
        marca = f"⟦{i}⟧"
        novo = re.sub(rf"(?<!\w){re.escape(termo)}(?!\w)", marca, texto, flags=re.IGNORECASE)
        if novo != texto:
            marcas[marca] = termo
            texto = novo
    return texto, marcas


def _restaurar(texto: str, marcas: dict[str, str]) -> str:
    for marca, termo in marcas.items():
        texto = texto.replace(marca, termo)
    return re.sub(r"⟦\d+⟧", "", texto)


# ---------------------------------------------------------------------- tradução
def _prompt(destino: idiomas.Idioma, origem: idiomas.Idioma | None, gl: dict,
            para_dublagem: bool) -> str:
    regras = [
        f"Traduza cada linha numerada para {destino.instrucao or destino.nome}.",
        "Mantenha a numeração [n] exatamente, uma linha por número, sem juntar nem dividir.",
        "Não traduza nem altere marcas como ⟦0⟧, ⟦1⟧.",
        "Responda só com as linhas traduzidas, sem comentários.",
        "Mantenha o tom (informal, técnico, engraçado) e as gírias com equivalentes naturais.",
    ]
    if origem:
        regras.insert(0, f"O texto original está em {origem.nome}.")
    if para_dublagem:
        regras.append("É para dublagem: use frases com número de sílabas parecido com o "
                      "original, para a fala caber no mesmo tempo.")
    if gl.get("traducoes"):
        fixas = "; ".join(f"{a} → {b}" for a, b in list(gl["traducoes"].items())[:60])
        regras.append(f"Use sempre estas traduções: {fixas}.")
    return "\n".join(f"- {r}" for r in regras)


def _ler_numeradas(resposta: str) -> dict[int, str]:
    saida: dict[int, str] = {}
    for linha in (resposta or "").splitlines():
        achado = re.match(r"\s*\[(\d+)\]\s*(.*)", linha)
        if achado and achado.group(2).strip():
            saida[int(achado.group(1))] = achado.group(2).strip()
    return saida


def traduzir_textos(textos: list[str], destino: str, llm: Llm, origem: str = "",
                    projeto: str = "", para_dublagem: bool = False, lote: int = 25,
                    progresso=None, cancelado=None) -> list[str]:
    alvo = idiomas.idioma(destino)
    de = idiomas.idioma(origem) if origem else None
    gl = glossario(projeto) if projeto else {"manter": [], "traducoes": {}}
    sistema = ("Você é um tradutor e legendador profissional.\n"
               + _prompt(alvo, de, gl, para_dublagem))
    saida: list[str] = list(textos)
    for comeco in range(0, len(textos), lote):
        if cancelado and cancelado():
            raise ErroEstudio("Cancelado.")
        grupo = list(range(comeco, min(len(textos), comeco + lote)))
        protegidos = {i: _proteger(textos[i], gl["manter"]) for i in grupo}
        pedido = "\n".join(f"[{i - comeco + 1}] {protegidos[i][0]}" for i in grupo)
        lidas = _ler_numeradas(llm([{"role": "system", "content": sistema},
                                    {"role": "user", "content": pedido}]))
        for i in grupo:
            traduzida = lidas.get(i - comeco + 1)
            if not traduzida:  # faltou: tenta a linha sozinha uma vez
                sozinha = _ler_numeradas(llm([{"role": "system", "content": sistema},
                                              {"role": "user",
                                               "content": f"[1] {protegidos[i][0]}"}]))
                traduzida = sozinha.get(1)
            if traduzida:
                saida[i] = _restaurar(traduzida, protegidos[i][1])
        if progresso:
            progresso(min(1.0, (grupo[-1] + 1) / max(1, len(textos))),
                      f"Traduzindo… {grupo[-1] + 1} de {len(textos)}")
    return saida


def traduzir(trechos: list[Trecho], destino: str, llm: Llm, origem: str = "",
             projeto: str = "", para_dublagem: bool = False, progresso=None,
             cancelado=None) -> list[Trecho]:
    textos = traduzir_textos([t.texto.replace("\n", " ") for t in trechos], destino, llm,
                             origem, projeto, para_dublagem, progresso=progresso,
                             cancelado=cancelado)
    return [Trecho(t.inicio, t.fim, novo, t.falante) for t, novo in zip(trechos, textos)]


# ---------------------------------------------------------------------- IA do Optimus
def llm_do_optimus(motor, modelo: str) -> Llm:
    """Adapta o motor do Optimus (local ou na nuvem) para a tradução."""

    def chamar(mensagens: list[dict]) -> str:
        resposta = motor.conversar(mensagens, modelo, None, {"temperature": 0.2})
        return getattr(resposta, "texto", "") or ""

    return chamar


def llm_do_contexto(ctx) -> Llm:
    agente = getattr(ctx, "agente", None)
    if agente is not None and getattr(agente, "motor", None) is not None:
        return llm_do_optimus(agente.motor, agente.modelo_principal())
    from optimus.app import Optimus

    optimus = Optimus(ctx.config) if getattr(ctx, "config", None) else Optimus()
    return llm_do_optimus(optimus.motor, optimus.modelo_atual())
