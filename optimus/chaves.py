"""Cofre de chaves: guarda chaves de API e senhas no cofre do próprio sistema.

Em vez de deixar a chave escrita no `config.toml`, o Optimus guarda no cofre do sistema
operacional (Gerenciador de Credenciais do Windows, Chaves do macOS, Secret Service/KWallet
no Linux), que é criptografado e ligado à sua conta. No `config.toml` fica só uma referência:

    chave_api = "cofre:motor.chave_api"

Qualquer campo de configuração aceita essa referência. Sem o pacote `keyring` instalado
(`pip install keyring`), tudo continua funcionando com a chave no arquivo, como antes.

Comandos: `optimus chaves listar | definir NOME | apagar NOME | migrar`.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

SERVICO = "open-optimus"
PREFIXO = "cofre:"

# Campos de configuração que guardam segredos (secao, chave). Destinos têm chave_api cada um.
CAMPOS_SECRETOS = [("motor", "chave_api"), ("voz", "elevenlabs_chave"), ("web", "senha"),
                   ("web", "token_comando"), ("casa", "token"),
                   ("estudio", "servidor_voz_chave")]


def _keyring():
    try:
        import keyring  # type: ignore[import-not-found]
        from keyring.backends import fail  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None  # sem cofre de verdade no sistema
    except Exception:  # noqa: BLE001
        return None
    return keyring


def disponivel() -> bool:
    return _keyring() is not None


def eh_referencia(valor: Any) -> bool:
    return isinstance(valor, str) and valor.startswith(PREFIXO)


def obter(nome: str) -> str:
    kr = _keyring()
    if not kr:
        return ""
    try:
        return kr.get_password(SERVICO, nome) or ""
    except Exception as erro:  # noqa: BLE001 - cofre trancado, D-Bus fora do ar...
        log.warning("Não consegui ler %s do cofre: %s", nome, erro)
        return ""


def guardar(nome: str, valor: str) -> bool:
    kr = _keyring()
    if not kr or not valor:
        return False
    try:
        kr.set_password(SERVICO, nome, valor)
        return True
    except Exception as erro:  # noqa: BLE001
        log.warning("Não consegui gravar %s no cofre: %s", nome, erro)
        return False


def apagar(nome: str) -> bool:
    kr = _keyring()
    if not kr:
        return False
    try:
        kr.delete_password(SERVICO, nome)
        return True
    except Exception:  # noqa: BLE001 - não existia
        return False


def resolver(valor: Any) -> Any:
    """Troca "cofre:nome" pelo valor guardado no cofre. Outros valores passam direto."""
    if eh_referencia(valor):
        return obter(valor[len(PREFIXO):])
    return valor


def referencias(config) -> list[dict[str, Any]]:
    """Onde há segredos na configuração e se estão no cofre ou ainda no arquivo."""
    saida = []
    for secao, chave in CAMPOS_SECRETOS:
        bruto = config.dados.get(secao, {}).get(chave, "")
        if bruto:
            saida.append({"campo": f"{secao}.{chave}", "no_cofre": eh_referencia(bruto)})
    for i, destino in enumerate(config.dados.get("destinos") or []):
        if destino.get("chave_api"):
            saida.append({"campo": f"destinos[{i}].chave_api ({destino.get('nome', '')})",
                          "no_cofre": eh_referencia(destino["chave_api"])})
    for nome, valor in (config.dados.get("provedores") or {}).items():
        if nome.endswith("_chave") and valor:
            saida.append({"campo": f"provedores.{nome}", "no_cofre": eh_referencia(valor)})
    return saida


def migrar(config) -> dict[str, Any]:
    """Move para o cofre os segredos escritos no config.toml e deixa só a referência."""
    if not disponivel():
        return {"ok": False, "erro": "Cofre do sistema indisponível. Instale com: "
                                     "pip install keyring"}
    movidos = []

    def mover(dicionario: dict, chave: str, nome: str):
        valor = dicionario.get(chave)
        if valor and not eh_referencia(valor) and guardar(nome, str(valor)):
            dicionario[chave] = PREFIXO + nome
            movidos.append(nome)

    for secao, chave in CAMPOS_SECRETOS:
        mover(config.dados.setdefault(secao, {}), chave, f"{secao}.{chave}")
    for i, destino in enumerate(config.dados.get("destinos") or []):
        mover(destino, "chave_api", f"destinos.{destino.get('nome') or i}.chave_api")
    provedores = config.dados.get("provedores") or {}
    for nome in list(provedores):
        if nome.endswith("_chave"):
            mover(provedores, nome, f"provedores.{nome}")
    if movidos and getattr(config, "caminho", None):
        config.salvar()
    return {"ok": True, "movidos": movidos,
            "mensagem": (f"{len(movidos)} segredo(s) movido(s) para o cofre do sistema."
                         if movidos else "Nenhum segredo solto no config.toml.")}
