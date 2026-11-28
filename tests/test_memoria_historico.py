from optimus.banco import Banco
from optimus.config import Config
from optimus.tools import ferramentas_ativas
from optimus.roteador import selecionar_ferramentas


def test_perguntas_de_contexto_anterior_habilitam_busca_no_historico(tmp_path):
    ferramentas = ferramentas_ativas(Config())
    selecionadas = selecionar_ferramentas(
        "qual resultado? o que decidimos na conversa anterior?", ferramentas)
    assert "buscar_conversas" in selecionadas


def test_historico_de_conversas_retorna_decisoes_anteriores(tmp_path):
    banco = Banco(tmp_path / "historico.sqlite")
    conversa = banco.nova_conversa("Pesquisa BRB")
    banco.adicionar_mensagem(conversa, "user", "Pesquise as ações do BRB Banco de Brasília.")
    banco.adicionar_mensagem(conversa, "assistant", "Os tickers relacionados são BSLI3 e BSLI4.")
    achados = banco.buscar_mensagens("BRB BSLI3")
    assert achados
    assert any("BSLI3" in item["trecho"] for item in achados)


def test_pergunta_sobre_acoes_brB_vai_para_pesquisa_web():
    from optimus.roteador import pre_execucao

    texto = "valor das ações do banco BRB hoje?"
    assert pre_execucao(texto) == ("pesquisar_web", {"consulta": "valor das acoes do banco brb hoje"})
    ferramentas = ferramentas_ativas(Config())
    selecionadas = selecionar_ferramentas(texto, ferramentas)
    assert "pesquisar_web" in selecionadas
    assert "cotacao" not in selecionadas
