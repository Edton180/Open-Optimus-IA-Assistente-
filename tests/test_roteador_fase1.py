"""O roteador oferece ao modelo as ferramentas novas (atualização, modelos, biblioteca, MCP)."""

from optimus.roteador import selecionar_ferramentas
from optimus.tools.base import Ferramenta

NOMES = ["atualizacao_verificar", "atualizacao_baixar", "atualizacao_voltar",
         "modelos_recomendados", "modelo_cabe", "modelo_avaliar", "biblioteca_listar",
         "consultar_conhecimento", "pesquisar_web"]
DISPONIVEIS = {n: Ferramenta(n, "x", {}, None) for n in NOMES}
DISPONIVEIS["mcp_notion_buscar"] = Ferramenta("mcp_notion_buscar", "[notion] Busca", {}, None)


def _sel(texto):
    return set(selecionar_ferramentas(texto, DISPONIVEIS))


def test_atualizacao():
    assert "atualizacao_verificar" in _sel("Optimus, tem atualização?")
    assert "atualizacao_voltar" in _sel("volta para a versão anterior")


def test_modelos():
    assert "modelo_cabe" in _sel("o modelo gemma4:31b cabe no meu PC?")
    assert "modelo_avaliar" in _sel("testa esse modelo novo")
    assert "modelos_recomendados" in _sel("qual o melhor modelo pra mim?")


def test_biblioteca_e_mcp():
    assert "biblioteca_listar" in _sel("o que tem na minha biblioteca?")
    assert _sel("procura no notion a ata de ontem") == {"mcp_notion_buscar"}
    assert "mcp_notion_buscar" not in _sel("procura minhas notas")


def test_conversa_comum_sem_ferramentas():
    assert _sel("oi, tudo bem?") == set()
