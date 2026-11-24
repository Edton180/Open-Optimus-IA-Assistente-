from optimus.tools import internet


class ConfigFake:
    def get(self, secao, chave, padrao=None):
        return 5 if (secao, chave) == ("internet", "max_resultados") else padrao


class ContextoFake:
    config = ConfigFake()


def test_expande_sigla_financeira_sem_perder_consulta_original():
    variantes = internet._variantes_consulta("ações BRB hoje")
    assert variantes[0] == "ações BRB hoje"
    assert "BSLI3" in variantes[1] and "BSLI4" in variantes[1]
    assert "Banco de Brasília" in variantes[1]


def test_resultados_sem_relacao_sao_reprovados():
    variantes = internet._variantes_consulta("ações BRB hoje")
    irrelevante = {"nome": "Internet: uma rede global", "trecho": "Como funciona a internet",
                   "link": "https://example.org/internet"}
    relevante = {"nome": "BRB Banco de Brasília: ações BSLI3 e BSLI4",
                 "trecho": "Cotação das ações do Banco de Brasília na B3",
                 "link": "https://ri.brb.com.br/acoes"}
    assert internet._pontuar_resultado(irrelevante, variantes) < 0.16
    assert internet._pontuar_resultado(relevante, variantes) >= 0.16


def test_pesquisa_combina_fontes_e_filtra_lixo(monkeypatch):
    chamadas = []

    def buscar(consulta, limite):
        chamadas.append(consulta)
        if "BSLI3" in consulta:
            return [
                {"nome": "BRB Banco de Brasília - ações BSLI3 e BSLI4",
                 "link": "https://ri.brb.com.br/acoes?utm_source=busca",
                 "trecho": "Cotação das ações do Banco de Brasília na B3."},
                {"nome": "Internet: rede mundial", "link": "https://example.org/internet",
                 "trecho": "Como funciona a internet."},
            ]
        return [
            {"nome": "Narcóticos Anônimos", "link": "https://example.org/na",
             "trecho": "Grupo de apoio e reuniões."},
            {"nome": "Dicas de segurança na internet", "link": "https://example.org/seguranca",
             "trecho": "Proteja suas contas online."},
        ]

    monkeypatch.setattr(internet, "BUSCADORES",
                        [("Motor A", buscar), ("Motor B", buscar), ("Motor C", buscar)])
    resultado = internet.pesquisar_web(ContextoFake(), "ações BRB hoje")
    assert resultado["itens"]
    assert all("BRB" in item["nome"] for item in resultado["itens"])
    assert resultado["itens"][0]["relevancia"] >= 0.16
    assert "Narcóticos Anônimos" not in str(resultado)
    assert any("BSLI3" in consulta for consulta in chamadas)


def test_pesquisa_diz_quando_nao_ha_resultados_relevantes(monkeypatch):
    def buscar(consulta, limite):
        return [{"nome": "Receita de bolo", "link": "https://example.org/bolo",
                 "trecho": "Farinha, ovos e açúcar."}]

    monkeypatch.setattr(internet, "BUSCADORES", [("Motor", buscar)])
    resultado = internet.pesquisar_web(ContextoFake(), "cotação das ações BRB")
    assert "erro" in resultado
    assert "relação suficiente" in resultado["erro"]


def test_bing_redireciona_para_url_real():
    import base64

    destino = "https://ri.brb.com.br/acoes"
    codificado = base64.urlsafe_b64encode(destino.encode()).decode().rstrip("=")
    redirecionamento = "https://www.bing.com/ck/a?u=a1" + codificado
    pagina = (
        '<li class="b_algo"><h2><a href="' + redirecionamento +
        '">BRB Banco de Brasília</a></h2><p>Ações BSLI3 e BSLI4</p></li>'
    )
    itens = internet.ler_bing_html(pagina)
    assert itens[0]["link"] == destino

def test_pesquisa_especifica_nao_aprova_resultado_por_uma_palavra_generica():
    variantes = internet._variantes_consulta("ações BRB hoje")
    resultado = {
        "nome": "Internet: uma rede global",
        "trecho": "Ações e investimentos em tecnologia para a internet.",
        "link": "https://example.org/internet",
    }
    assert internet._pontuar_resultado(resultado, variantes) == 0.0
