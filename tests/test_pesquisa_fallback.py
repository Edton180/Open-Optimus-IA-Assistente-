import json

from optimus.agent import _resposta_pesquisa_sem_modelo


def test_preserva_resultados_quando_motor_ia_nao_responde():
    bruto = json.dumps({
        "consulta": "ações BRB hoje",
        "itens": [{
            "nome": "BRB Banco de Brasília",
            "trecho": "Resultado sobre ações BSLI3 e BSLI4.",
            "link": "https://ri.brb.com.br/acoes",
            "data": "2026-11-24",
        }],
    }, ensure_ascii=False)
    resposta = _resposta_pesquisa_sem_modelo("pesquisar_web", bruto)
    assert "motor de IA não respondeu" in resposta
    assert "BRB Banco de Brasília" in resposta
    assert "https://ri.brb.com.br/acoes" in resposta


def test_nao_inventa_resultado_quando_busca_falha():
    bruto = json.dumps({"erro": "Nenhum resultado relevante"})
    resposta = _resposta_pesquisa_sem_modelo("pesquisar_web", bruto)
    assert "Nenhum resultado relevante" in resposta
    assert "BRB Banco de Brasília" not in resposta
