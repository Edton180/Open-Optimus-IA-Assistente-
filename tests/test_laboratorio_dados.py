from types import SimpleNamespace

from optimus.tools.laboratorio_dados import laboratorio_dados


def executar(op, valor):
    return laboratorio_dados(SimpleNamespace(), op, valor)


def test_base64_roundtrip():
    codificado = executar("base64_codificar", "Olá Optimus")
    assert executar("base64_decodificar", codificado["resultado"])["resultado"] == "Olá Optimus"


def test_hash_sha256():
    import hashlib
    resultado = executar("sha256", "Optimus")
    assert resultado["resultado"] == hashlib.sha256(b"Optimus").hexdigest()


def test_url_html_and_hex():
    assert executar("url_codificar", "a b")["resultado"] == "a%20b"
    assert executar("html_escapar", "<b>")["resultado"] == "&lt;b&gt;"
    assert executar("hex_decodificar", "4f7074696d7573")["resultado"] == "Optimus"


def test_rejects_invalid_base64_and_unknown_operation():
    assert "erro" in executar("base64_decodificar", "não é base64!")
    assert "erro" in executar("inexistente", "texto")


def test_input_limit():
    assert "erro" in executar("sha256", "x" * (2 * 1024 * 1024 + 1))


def test_gzip_truncado_e_rejeitado():
    import base64
    import gzip
    conteudo = base64.b64encode(gzip.compress(b"conteudo de teste")[:-5]).decode("ascii")
    assert "erro" in executar("gzip_descomprimir", conteudo)
