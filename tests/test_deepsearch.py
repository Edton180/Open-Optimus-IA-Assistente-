from optimus.tools import deepsearch


class ContextoFake:
    pass


def test_planeja_pesquisa_em_tres_papeis():
    planos = deepsearch._subconsultas("Como funciona energia solar?")
    assert len(planos) == 3
    assert planos[0][1] == "Como funciona energia solar?"
    assert {p for p, _ in planos} == {
        "pesquisador_exato", "pesquisador_contexto", "pesquisador_fontes_primarias"
    }


def test_deepsearch_agrega_fontes_e_le_paginas(monkeypatch):
    chamadas = []

    def pesquisar(ctx, consulta, quantidade):
        chamadas.append(consulta)
        if "fundamentos" in consulta:
            titulo = "Fundamentos de energia solar"
            url = "https://www.gov.br/energia/solar"
        elif "fonte oficial" in consulta:
            titulo = "Dados oficiais de energia solar"
            url = "https://www.gov.br/dados/solar"
        else:
            titulo = "Energia solar: guia técnico"
            url = "https://universidade.edu.br/energia-solar"
        return {"itens": [{
            "nome": titulo, "link": url, "trecho": "Energia solar e geração fotovoltaica.",
            "relevancia": 0.8, "provedor": "Bing", "provedores": ["Bing"]
        }]}

    def ler(ctx, url):
        return {"titulo": "Energia solar", "texto":
                "A energia solar fotovoltaica converte luz em eletricidade. "
                "Sistemas fotovoltaicos geram energia renovável."}

    monkeypatch.setattr(deepsearch, "pesquisar_web", pesquisar)
    monkeypatch.setattr(deepsearch, "ler_pagina", ler)
    resultado = deepsearch.deepsearch(ContextoFake(), "energia solar", 8, True)

    assert len(chamadas) == 3
    assert resultado["modo"] == "deepsearch_paralelo"
    assert len(resultado["fontes"]) == 3
    assert resultado["equipes"][1]["resultado"]["fontes_unicas"] == 3
    assert all(f["pagina_lida"] for f in resultado["fontes"])
    assert all(f["evidencias"] for f in resultado["fontes"])


def test_deepsearch_nao_inventa_fontes_quando_busca_falha(monkeypatch):
    monkeypatch.setattr(deepsearch, "pesquisar_web", lambda *a: {"erro": "sem resultados"})
    resultado = deepsearch.deepsearch(ContextoFake(), "tema sem fontes", 8, False)
    assert resultado["fontes"] == [] if "fontes" in resultado else True
    assert "erro" in resultado


def test_dominio_oficial_brasileiro():
    assert deepsearch._dominio("https://www.gov.br/") == "gov.br"
    assert deepsearch._dominio("https://ri.brb.com.br/") == "brb.com.br"
