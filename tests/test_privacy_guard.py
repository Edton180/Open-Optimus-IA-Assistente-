"""Testes da barreira de privacidade (Zero-Leak).

Garantem que nenhum dado pessoal do dono do PC vaza em um commit automático.
"""

import pytest

from optimus import privacy_guard as pg


# --------------------------------------------------------------------------- arquivos proibidos
@pytest.mark.parametrize("caminho", [
    "banco.db", "optimus/dados.sqlite", "memoria.sqlite3", ".env", "prod.env",
    "config.toml", "chaves.pem", "id_rsa", "deploy.key", "credenciais.json",
    "memorias_longo_prazo.json", "historico_chats.json", "auditoria.jsonl",
    "optimus/gravacoes/portao.mp4", "backups/tudo.zip.db", "camera.mov",
])
def test_arquivos_proibidos(caminho):
    assert pg.eh_arquivo_proibido(caminho)


@pytest.mark.parametrize("caminho", [
    "optimus/privacy_guard.py", "README.md", "config.example.toml",
    "docs/seguranca.md", "optimus/knowledge/hacking.md", "tests/test_x.py",
])
def test_arquivos_permitidos(caminho):
    assert not pg.eh_arquivo_proibido(caminho)


def test_pasta_proibida_pega_qualquer_arquivo():
    assert pg.eh_arquivo_proibido("optimus/backups/qualquer.txt")
    assert pg.eh_arquivo_proibido("dados_usuario/perfil.yaml")


# --------------------------------------------------------------------------- segredos mascarados
# Os segredos de teste são montados por partes (prefixo + corpo) de propósito: assim o texto
# fonte não contém um token completo que o secret-scanning do GitHub bloquearia, mas em tempo
# de execução a string testa o regex do mesmo jeito.
_C = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"  # corpo genérico sem significado
_SK = "sk-" + "openaistylekey0123456789abcdef"  # chave fake montada por partes
_GHP = "ghp_" + _C


@pytest.mark.parametrize("prefixo,corpo,marcador", [
    ("sk-", "abc123def456ghi789jkl012mno", "<SUA_API_KEY>"),
    ("sk-ant-", "api03aaaaaaaaaaaaaaaaaaaaaa", "<SUA_API_KEY>"),
    ("ghp_", _C, "<SEU_GITHUB_TOKEN>"),
    ("AIza", "SyA1234567890abcdefghijklmnopqrstuv", "<SUA_API_KEY>"),
    ("gsk_", _C, "<SUA_API_KEY>"),
    ("xox" + "b-", "123456789012-abcdefghijklmno", "<SEU_TOKEN>"),
    ("AKIA", "IOSFODNN7EXAMPL0", "<SUA_AWS_KEY>"),
])
def test_mascara_chaves(prefixo, corpo, marcador):
    segredo = prefixo + corpo
    saida = pg.mascarar(f"valor = {segredo}")
    assert marcador in saida
    assert segredo not in saida  # o segredo cru não pode sobrar


def test_mascara_chave_privada():
    texto = ("-----BEGIN RSA PRIVATE KEY-----\n"
             "MIIEowIBAAKCAQEA1234567890\nabcdefg\n"
             "-----END RSA PRIVATE KEY-----")
    saida = pg.mascarar(texto)
    assert "<CHAVE_PRIVADA>" in saida
    assert "MIIEowIBAAKCAQEA" not in saida


def test_mascara_atribuicao_senha_e_wifi():
    assert "<SUA_SENHA>" in pg.mascarar('password = "minhaSenha123"')
    assert "<SUA_SENHA_WIFI>" in pg.mascarar('wpa_psk = "casa-segredo-2024"')
    assert "<SEU_TOKEN>" in pg.mascarar("token: meuTokenSecretoAqui")


def test_mascara_ip_e_mac():
    saida = pg.mascarar("meu IP é 192.168.1.42 e o MAC AA:BB:CC:DD:EE:FF")
    assert "<SEU_IP>" in saida and "192.168.1.42" not in saida
    assert "<SEU_MAC>" in saida and "AA:BB:CC:DD:EE:FF" not in saida


def test_mascara_caminhos_de_usuario():
    assert pg.mascarar(r"C:\Users\Kaik\optimus") == r"C:\Users\<USUARIO>\optimus"
    assert pg.mascarar("/home/kaik/.config") == "/home/<USUARIO>/.config"
    assert pg.mascarar("/Users/kaik/Documents") == "/Users/<USUARIO>/Documents"


# --------------------------------------------------------------------------- falsos positivos
def test_nao_mascara_ips_seguros():
    for ip in ("127.0.0.1", "0.0.0.0", "8.8.8.8"):
        assert ip in pg.mascarar(f"host = {ip}")


def test_nao_mascara_numero_de_versao():
    # 1.2.3.400 tem octeto > 255: não é IP, não deve virar <SEU_IP>
    assert "<SEU_IP>" not in pg.mascarar("versao 1.2.3.400")


def test_nao_mascara_placeholder_de_usuario():
    assert pg.mascarar("/home/usuario/x") == "/home/usuario/x"
    assert pg.mascarar(r"C:\Users\<USUARIO>\x") == r"C:\Users\<USUARIO>\x"


def test_nao_mascara_valores_vazios_ou_placeholder():
    assert pg.mascarar('chave_api = ""') == 'chave_api = ""'
    assert pg.mascarar('token = "<SEU_TOKEN>"') == 'token = "<SEU_TOKEN>"'


def test_texto_limpo_fica_intacto():
    texto = "def soma(a, b):\n    return a + b  # função normal\n"
    assert pg.mascarar(texto) == texto
    assert pg.achados(texto) == []


# --------------------------------------------------------------------------- revisão de diff
def _diff(arquivo: str, linhas_add: list[str]) -> str:
    corpo = "\n".join("+" + l for l in linhas_add)
    return (f"diff --git a/{arquivo} b/{arquivo}\n"
            f"--- a/{arquivo}\n+++ b/{arquivo}\n"
            f"@@ -0,0 +1,{len(linhas_add)} @@\n{corpo}\n")


def test_diff_limpo_e_seguro():
    diff = _diff("optimus/x.py", ["def f():", "    return 1"])
    rel = pg.revisar_diff(diff)
    assert rel.seguro
    assert rel.resumo().startswith("Nenhum dado")


def test_diff_com_segredo_nao_e_seguro():
    diff = _diff("optimus/x.py", [f"API_KEY = '{_SK}'"])
    rel = pg.revisar_diff(diff)
    assert not rel.seguro
    assert rel.achados
    assert rel.achados[0].linha == 1


def test_diff_com_arquivo_proibido_e_bloqueado():
    diff = _diff("config.toml", [f'chave_api = "{_SK}"'])
    rel = pg.revisar_diff(diff)
    assert not rel.seguro
    assert "config.toml" in rel.arquivos_bloqueados


def test_diff_ignora_linhas_removidas():
    diff = ("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
            f"@@ -1,1 +1,1 @@\n-API_KEY = '{_SK}'\n"
            "+API_KEY = os.environ['OPENAI_KEY']\n")
    rel = pg.revisar_diff(diff)
    assert rel.seguro  # a linha com o segredo está sendo REMOVIDA


def test_revisar_arquivos():
    rel = pg.revisar_arquivos({
        "optimus/ok.py": "x = 1\n",
        "optimus/vaza.py": "senha = 'segredoReal123'\n",
        "memoria.json": "{...}",
    })
    assert not rel.seguro
    assert "memoria.json" in rel.arquivos_bloqueados
    assert any(a.tipo == "atribuicao" for a in rel.achados)
