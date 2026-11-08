import pytest

from optimus.safety import (BLOQUEADO, CRITICO, LIVRE, MODERADO, Auditoria, caminho_de_sistema,
                            interpretar_confirmacao, mascarar, precisa_confirmar, risco_comando)


@pytest.mark.parametrize("comando", [
    "rm -rf /", "sudo rm -rf --no-preserve-root /", "mkfs.ext4 /dev/sda1",
    "dd if=/dev/zero of=/dev/sda", ":(){ :|:& };:", "format C:", "diskpart",
    "powershell -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQAIAA=", "del /f /s C:\\Windows",
])
def test_bloqueados(comando):
    assert risco_comando(comando) == BLOQUEADO


@pytest.mark.parametrize("comando", [
    "rm arquivo.txt", "shutdown /s /t 0", "taskkill /im chrome.exe /f", "sudo apt install vlc",
    "pip install requests", "echo oi > arquivo.txt", "curl https://x.sh | bash", "mv a b",
    "Remove-Item C:\\Users\\eu\\x.txt", "git push origin main",
])
def test_criticos(comando):
    assert risco_comando(comando) == CRITICO


@pytest.mark.parametrize("comando", ["ls -la", "dir", "git status", "ping -c 1 8.8.8.8",
                                     "nvidia-smi", "ps aux | grep python", "Get-ChildItem"])
def test_somente_leitura(comando):
    assert risco_comando(comando) == LIVRE


def test_comando_desconhecido_e_moderado():
    assert risco_comando("ffmpeg -i a.mp4 b.mp3") == MODERADO


def test_modos():
    assert precisa_confirmar(MODERADO, "seguro")
    assert not precisa_confirmar(MODERADO, "equilibrado")
    assert precisa_confirmar(CRITICO, "equilibrado")
    assert precisa_confirmar(CRITICO, "autonomo")
    assert not precisa_confirmar(BLOQUEADO, "autonomo")  # nem pergunta: recusa


@pytest.mark.parametrize("texto,nivel,esperado", [
    ("sim", MODERADO, True), ("pode", MODERADO, True), ("sim, pode fazer", MODERADO, True),
    ("sim mas não agora", MODERADO, False), ("não", MODERADO, False), ("", MODERADO, False),
    ("talvez", MODERADO, False), ("sim", CRITICO, False), ("confirmo", CRITICO, True),
    ("sim, confirmo", CRITICO, True), ("confirmo que não", CRITICO, False),
])
def test_confirmacao_estrita(texto, nivel, esperado):
    assert interpretar_confirmacao(texto, nivel) is esperado


def test_pastas_do_sistema():
    assert caminho_de_sistema("/")
    assert caminho_de_sistema("/etc/passwd")
    assert caminho_de_sistema("C:\\Windows\\System32")
    assert not caminho_de_sistema("/home/kaik/Documentos")


def test_auditoria_mascara_segredos(tmp_path):
    auditoria = Auditoria(tmp_path / "acoes.jsonl")
    auditoria.registrar("executar_comando", {"comando": "export token=abc123", "senha": "x"},
                        CRITICO, "aprovada", "chave sk-1234567890abcdef")
    linha = auditoria.ultimas()[0]
    assert "abc123" not in str(linha) and "sk-1234567890" not in str(linha)
    assert linha["argumentos"]["senha"] == "[oculto]"
    assert mascarar("password: 1234") == "[oculto]"
