"""Testes da base de conhecimento embutida (optimus/conhecimento.py).

Cobrem: indexação dos .md no banco, idempotência (só reindexa o que mudou), remoção de fontes
que sumiram, e que os arquivos embutidos de verdade estão lá e são pesquisáveis.
"""

from optimus import conhecimento
from optimus.banco import Banco


def _banco(tmp_path) -> Banco:
    return Banco(tmp_path / "db.sqlite")


def _escrever(pasta, nome, texto):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{nome}.md").write_text(texto, encoding="utf-8")


# --------------------------------------------------------------- indexação básica
def test_indexa_e_torna_pesquisavel(tmp_path):
    pasta = tmp_path / "knowledge"
    _escrever(pasta, "gatos", "# Gatos\n\nO gato é um animal doméstico que ronrona.")
    banco = _banco(tmp_path)

    resumo = conhecimento.indexar_embutido(banco, pasta, tmp_path / "estado.json")

    assert resumo["indexados"] == 1
    assert resumo["total"] == 1
    achados = banco.consultar("gato ronrona")
    assert achados
    assert achados[0]["fonte"] == "embutido:gatos"
    assert achados[0]["titulo"] == "Gatos"


def test_titulo_cai_no_nome_do_arquivo_sem_cabecalho(tmp_path):
    pasta = tmp_path / "knowledge"
    _escrever(pasta, "notas", "Texto sem cabeçalho nenhum aqui.")
    banco = _banco(tmp_path)

    conhecimento.indexar_embutido(banco, pasta, tmp_path / "estado.json")

    fontes = {f["fonte"]: f["titulo"] for f in banco.fontes()}
    assert fontes["embutido:notas"] == "notas"


# --------------------------------------------------------------- idempotência
def test_nao_reindexa_quando_nada_muda(tmp_path):
    pasta = tmp_path / "knowledge"
    _escrever(pasta, "a", "# A\n\nConteúdo A.")
    banco = _banco(tmp_path)
    estado = tmp_path / "estado.json"

    primeiro = conhecimento.indexar_embutido(banco, pasta, estado)
    segundo = conhecimento.indexar_embutido(banco, pasta, estado)

    assert primeiro["indexados"] == 1
    assert segundo["indexados"] == 0  # inalterado: não reindexa


def test_reindexa_quando_conteudo_muda(tmp_path):
    pasta = tmp_path / "knowledge"
    _escrever(pasta, "a", "# A\n\nConteúdo A.")
    banco = _banco(tmp_path)
    estado = tmp_path / "estado.json"

    conhecimento.indexar_embutido(banco, pasta, estado)
    _escrever(pasta, "a", "# A\n\nConteúdo A bem diferente agora.")
    segundo = conhecimento.indexar_embutido(banco, pasta, estado)

    assert segundo["indexados"] == 1
    achados = banco.consultar("diferente agora")
    assert achados


# --------------------------------------------------------------- remoção
def test_remove_fonte_que_sumiu(tmp_path):
    pasta = tmp_path / "knowledge"
    _escrever(pasta, "a", "# A\n\nConteúdo A.")
    _escrever(pasta, "b", "# B\n\nConteúdo B.")
    banco = _banco(tmp_path)
    estado = tmp_path / "estado.json"

    conhecimento.indexar_embutido(banco, pasta, estado)
    (pasta / "b.md").unlink()
    resumo = conhecimento.indexar_embutido(banco, pasta, estado)

    assert resumo["removidos"] == 1
    fontes = {f["fonte"] for f in banco.fontes()}
    assert "embutido:b" not in fontes
    assert "embutido:a" in fontes


# --------------------------------------------------------------- conteúdo real embutido
def test_arquivos_embutidos_de_verdade_existem(tmp_path):
    banco = _banco(tmp_path)
    resumo = conhecimento.indexar_embutido(banco, estado_arq=tmp_path / "estado.json")

    assert resumo["total"] >= 5  # sobre_optimus, base, socorros, conversoes, redes, programacao
    assert banco.consultar("primeiros socorros engasgo")
    assert banco.consultar("converter celsius fahrenheit")


def test_pasta_inexistente_nao_quebra(tmp_path):
    banco = _banco(tmp_path)
    resumo = conhecimento.indexar_embutido(banco, tmp_path / "nao_existe",
                                           tmp_path / "estado.json")
    assert resumo == {"indexados": 0, "removidos": 0, "total": 0}
