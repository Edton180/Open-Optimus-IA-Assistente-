"""Motor OmniVoice (k2-fsa, licença Apache-2.0): clonagem, criação de voz por descrição e
mais de 600 idiomas num modelo só.

- **Clonar**: alguns segundos de amostra bastam; a "impressão" da voz é calculada uma vez e
  guardada na pasta do perfil, então as próximas gerações começam na hora.
- **Criar por descrição**: "voz feminina idosa, grave, sussurrando" vira os atributos que o
  modelo entende (gênero, idade, tom, estilo, sotaque).
- **Duração exata**: na dublagem, cada fala pode ser gerada já com o tempo do trecho original.
- **Sons sem palavras**: [risada], [suspiro], [respiração]... viram as marcas do modelo.

Opcional: `pip install omnivoice` (usa PyTorch; o modelo vem do Hugging Face na primeira vez).
"""

from __future__ import annotations

import importlib.util
import re
import threading
import unicodedata
from pathlib import Path

from optimus.estudio.audio import ErroEstudio

REPOSITORIO = "k2-fsa/OmniVoice"
TAXA = 24000
_MODELO: dict[str, object] = {}
_PROMPTS: dict[str, object] = {}
_TRAVA = threading.Lock()

# Marcas em português → marcas do OmniVoice
SONS = {
    "risada": "[laughter]", "riso": "[laughter]", "rindo": "[laughter]", "gargalhada": "[laughter]",
    "suspiro": "[sigh]", "suspira": "[sigh]", "respiracao": "[breath]", "respira": "[breath]",
    "tosse": "[cough]", "pigarro": "[cough]", "choro": "[crying]", "chorando": "[crying]",
    "bocejo": "[yawn]", "hum": "[hmm]", "hmm": "[hmm]",
}

# Palavras da descrição → atributos do modelo (em inglês, como ele foi treinado)
_ATRIBUTOS: list[tuple[tuple[str, ...], str]] = [
    (("feminina", "mulher", "moca", "senhora", "garota"), "female"),
    (("masculina", "homem", "rapaz", "senhor", "garoto"), "male"),
    (("crianca", "infantil"), "child"),
    (("jovem", "adolescente"), "young adult"),
    (("adulta", "adulto", "madura", "maduro"), "middle-aged"),
    (("idosa", "idoso", "velha", "velho", "anciao", "avo"), "elderly"),
    (("grave", "profunda", "encorpada", "trovao"), "low pitch"),
    (("aguda", "fina"), "high pitch"),
    (("sussurro", "sussurrando", "asmr", "baixinho"), "whisper"),
    (("rouca", "rouco"), "hoarse"),
    (("britanico", "britanica", "inglaterra"), "british accent"),
    (("americano", "americana"), "american accent"),
    (("australiano", "australiana"), "australian accent"),
    (("indiano", "indiana"), "indian accent"),
    (("portugues", "portuguesa", "lusitano"), "portuguese accent"),
    (("brasileiro", "brasileira"), "brazilian accent"),
]


def instalado() -> bool:
    try:
        return importlib.util.find_spec("omnivoice") is not None
    except (ImportError, ValueError):
        return False


def _normal(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def instrucao(descricao: str, genero: str = "") -> str:
    """"voz masculina grave e idosa" → "male, elderly, low pitch"."""
    palavras = set(re.findall(r"[a-z]+", _normal(descricao)))
    saida: list[str] = []
    for chaves, atributo in _ATRIBUTOS:
        if palavras & set(chaves) and atributo not in saida:
            saida.append(atributo)
    if not ({"female", "male"} & set(saida)) and genero:
        saida.insert(0, "male" if genero.startswith("m") else "female")
    return ", ".join(saida)


def converter_sons(texto: str) -> str:
    """[risada] → [laughter]. Marcas desconhecidas ficam como estão."""
    def troca(m: re.Match) -> str:
        return SONS.get(_normal(m.group(1)).strip(), m.group(0))

    return re.sub(r"\[([^\]\d]{2,20})\]", troca, texto)


def _dispositivo() -> tuple[str, object]:
    import torch

    if torch.cuda.is_available():
        return "cuda:0", torch.float16
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", torch.float16
    return "cpu", torch.float32


def modelo():
    if not instalado():
        raise ErroEstudio("O motor OmniVoice não está instalado: pip install omnivoice "
                          "(clonagem e 600+ idiomas; o modelo vem do Hugging Face).")
    with _TRAVA:
        if "m" not in _MODELO:
            from omnivoice import OmniVoice

            local, tipo = _dispositivo()
            _MODELO["m"] = OmniVoice.from_pretrained(REPOSITORIO, device_map=local, dtype=tipo)
    return _MODELO["m"]


def _prompt(m, amostra: Path, texto_amostra: str = ""):
    """Calcula (ou lê do disco) a impressão da voz clonada."""
    chave = f"{amostra.resolve()}:{amostra.stat().st_mtime_ns}"
    if chave in _PROMPTS:
        return _PROMPTS[chave]
    guardado = amostra.with_suffix(".omnivoice.pt")
    prompt = None
    try:
        from omnivoice import VoiceClonePrompt

        if guardado.exists() and guardado.stat().st_mtime_ns >= amostra.stat().st_mtime_ns:
            prompt = VoiceClonePrompt.load(str(guardado))
    except Exception:  # noqa: BLE001 - versão sem cache: calcula de novo
        prompt = None
    if prompt is None and hasattr(m, "create_voice_clone_prompt"):
        argumentos = {"ref_audio": str(amostra)}
        if texto_amostra:
            argumentos["ref_text"] = texto_amostra
        prompt = m.create_voice_clone_prompt(**argumentos)
        try:
            prompt.save(str(guardado))
        except Exception:  # noqa: BLE001
            pass
    _PROMPTS[chave] = prompt
    return prompt


def gerar(texto: str, amostra: str | Path | None = None, descricao: str = "",
          genero: str = "", velocidade: float = 1.0, duracao: float = 0.0,
          passos: int = 32, texto_amostra: str = ""):
    """Texto → numpy float32 mono a 24 kHz.

    Com `amostra`: clona. Sem amostra e com `descricao`: cria a voz pelos atributos. Sem os
    dois: o modelo escolhe uma voz natural para o idioma do texto."""
    import numpy as np

    m = modelo()
    argumentos: dict = {"text": converter_sons(texto), "num_step": int(passos or 32)}
    if amostra:
        caminho = Path(amostra)
        if not caminho.exists():
            raise ErroEstudio("A amostra da voz sumiu. Clone de novo.")
        prompt = _prompt(m, caminho, texto_amostra)
        if prompt is not None:
            argumentos["voice_clone_prompt"] = prompt
        else:
            argumentos["ref_audio"] = str(caminho)
    else:
        pedido = instrucao(descricao, genero)
        if pedido:
            argumentos["instruct"] = pedido
    if duracao and duracao > 0:
        argumentos["duration"] = float(duracao)
    elif velocidade and abs(velocidade - 1) > 0.01:
        argumentos["speed"] = float(velocidade)
    saida = m.generate(**argumentos)
    onda = saida[0] if isinstance(saida, (list, tuple)) else saida
    try:
        onda = onda.squeeze().detach().cpu().numpy()
    except AttributeError:
        pass
    return np.asarray(onda, dtype="float32").reshape(-1)


def descarregar() -> None:
    with _TRAVA:
        _MODELO.clear()
        _PROMPTS.clear()
