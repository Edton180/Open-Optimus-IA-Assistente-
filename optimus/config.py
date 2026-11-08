"""Configuração do Optimus.

Fica em um arquivo TOML:
- Linux: ~/.config/optimus/config.toml (ou $XDG_CONFIG_HOME/optimus)
- Windows: %APPDATA%\\Optimus\\config.toml

A variável OPTIMUS_HOME troca a pasta inteira (útil para testes e instalações portáteis).
"""

from __future__ import annotations

import copy
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def pasta_base() -> Path:
    """Pasta onde ficam configuração, memória e registros."""
    if os.environ.get("OPTIMUS_HOME"):
        return Path(os.environ["OPTIMUS_HOME"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Optimus"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "optimus"


PERSONALIDADE_PADRAO = (
    "Você é o Optimus, um assistente de IA pessoal que roda no computador do usuário. "
    "Fale em português do Brasil, de forma educada, direta e com um toque de bom humor. "
    "Você tem ferramentas para pesquisar na internet, ler páginas, mexer em arquivos, abrir "
    "programas, executar comandos e ver o estado do sistema. Use as ferramentas sempre que "
    "elas ajudarem a dar uma resposta correta ou a cumprir o pedido, sem pedir licença para "
    "consultas simples. Quando terminar uma tarefa, diga em poucas palavras o que fez. "
    "Respostas faladas devem ser curtas."
)

PADRAO: dict[str, Any] = {
    "geral": {
        "nome": "Optimus",
        "usuario": "",
        "idioma": "pt-BR",
        # Texto de sistema. Pode ser trocado livremente pelo usuário.
        "personalidade": PERSONALIDADE_PADRAO,
    },
    "motor": {
        # ollama | openai (qualquer servidor compatível: llama.cpp, LM Studio, vLLM, nuvem) | demo
        "backend": "ollama",
        "url": "http://127.0.0.1:11434",
        "chave_api": "",
        # Vazio = escolhido pelo perfil de hardware
        "modelo": "",
        "modelo_rapido": "",
        "contexto": 0,
        "threads": 0,
        "temperatura": 0.6,
        "manter_carregado": "30m",
    },
    "agente": {
        "max_passos": 12,
        # seguro | equilibrado | autonomo
        "modo": "equilibrado",
        "pasta_trabalho": "",
    },
    "voz": {
        "palavra_ativacao": "optimus",
        # auto | faster-whisper | nenhum
        "stt": "auto",
        "modelo_stt": "",
        # auto | piper | sistema | edge | nenhum
        "tts": "auto",
        # feminina | masculina | id de uma voz (veja: optimus vozes)
        "voz": "feminina",
        "velocidade": 1.0,
        "falar_respostas": True,
    },
    "internet": {
        "buscador": "duckduckgo",
        "max_resultados": 5,
    },
    "web": {
        "host": "127.0.0.1",
        "porta": 8765,
        # Senha para acessar a interface de outro aparelho (celular). Vazio = só neste PC.
        "senha": "",
    },
    "recursos": {
        # Quanto do PC o Optimus pode usar: economico | equilibrado | maximo
        "uso": "equilibrado",
        # Abaixo desta RAM livre (GB) o Optimus troca para o modelo rápido para não travar o PC
        "ram_minima_gb": 1.5,
        "prioridade_baixa": True,
    },
    "ferramentas": {
        # Liga e desliga grupos de ferramentas
        "internet": True,
        "arquivos": True,
        "comandos": True,
        "programas": True,
        "teclado_mouse": False,
        "lembretes": True,
        "memoria": True,
        "casa": True,
        "plugins": True,
    },
    "casa": {
        # Home Assistant: http://IP:8123 e um token de longa duração (Perfil > Segurança)
        "url": "",
        "token": "",
    },
    # Outros computadores e outras IAs (veja docs/rede.md)
    "destinos": [],
}


def _mesclar(base: dict, extra: dict) -> dict:
    saida = copy.deepcopy(base)
    for chave, valor in extra.items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            saida[chave] = _mesclar(saida[chave], valor)
        else:
            saida[chave] = valor
    return saida


def _valor_toml(valor: Any) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return repr(valor)
    if isinstance(valor, list):
        return "[" + ", ".join(_valor_toml(v) for v in valor) + "]"
    texto = str(valor).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{texto}"'


def para_toml(dados: dict[str, dict[str, Any]]) -> str:
    linhas: list[str] = ["# Configuração do Optimus. Edite à vontade.", ""]
    for secao, valores in dados.items():
        if isinstance(valores, list):
            for item in valores:
                linhas.append(f"[[{secao}]]")
                for chave, valor in item.items():
                    linhas.append(f"{chave} = {_valor_toml(valor)}")
                linhas.append("")
            continue
        linhas.append(f"[{secao}]")
        for chave, valor in valores.items():
            linhas.append(f"{chave} = {_valor_toml(valor)}")
        linhas.append("")
    return "\n".join(linhas)


@dataclass
class Config:
    dados: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(PADRAO))
    caminho: Path | None = None

    def __getitem__(self, secao: str) -> dict[str, Any]:
        return self.dados[secao]

    def get(self, secao: str, chave: str, padrao: Any = None) -> Any:
        return self.dados.get(secao, {}).get(chave, padrao)

    def definir(self, secao: str, chave: str, valor: Any) -> None:
        self.dados.setdefault(secao, {})[chave] = valor

    def salvar(self, caminho: Path | None = None) -> Path:
        destino = caminho or self.caminho or (pasta_base() / "config.toml")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(para_toml(self.dados), encoding="utf-8")
        self.caminho = destino
        return destino


def converter_valor(texto: str) -> Any:
    """Converte texto digitado no terminal para o tipo certo."""
    baixo = texto.strip().lower()
    if baixo in ("true", "sim", "verdadeiro"):
        return True
    if baixo in ("false", "nao", "não", "falso"):
        return False
    try:
        return int(texto)
    except ValueError:
        pass
    try:
        return float(texto)
    except ValueError:
        return texto


def carregar(caminho: Path | None = None) -> Config:
    destino = caminho or (pasta_base() / "config.toml")
    dados = copy.deepcopy(PADRAO)
    if destino.exists():
        with open(destino, "rb") as arquivo:
            dados = _mesclar(dados, tomllib.load(arquivo))
    return Config(dados=dados, caminho=destino)
