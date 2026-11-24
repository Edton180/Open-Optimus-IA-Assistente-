"""Arquivos e pastas."""

from __future__ import annotations

import fnmatch
import os
import shutil
import tempfile
import time

from optimus.safety import BLOQUEADO, CRITICO, LIVRE, MODERADO, Avaliacao, caminho_de_sistema
from optimus.tools.base import ferramenta, numero, resolver, texto


@ferramenta(
    "listar_pasta",
    "Lista arquivos e pastas de um diretório. Aceita ~ para a pasta do usuário.",
    {"caminho": texto("Pasta a listar, por exemplo ~/Downloads")},
    grupo="arquivos",
)
def listar_pasta(ctx, caminho: str = "."):
    pasta = resolver(ctx, caminho)
    itens = []
    for entrada in sorted(pasta.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:300]:
        try:
            info = entrada.stat()
        except OSError:
            continue
        itens.append({"nome": entrada.name + ("/" if entrada.is_dir() else ""),
                      "tamanho_kb": round(info.st_size / 1024, 1) if entrada.is_file() else None,
                      "modificado": time.strftime("%Y-%m-%d %H:%M",
                                                  time.localtime(info.st_mtime))})
    return {"pasta": str(pasta), "total": len(itens), "itens": itens}


@ferramenta(
    "ler_arquivo",
    "Lê um arquivo de texto em blocos paginados de até 64 KB. Para arquivos grandes, repita "
    "a chamada usando o proximo_offset retornado até fim=true.",
    {"caminho": texto("Caminho do arquivo"),
     "offset": numero("Deslocamento em bytes (padrão 0)"),
     "limite_bytes": numero("Tamanho do bloco em bytes, máximo 65536")},
    grupo="arquivos", obrigatorios=["caminho"],
)
def ler_arquivo(ctx, caminho: str, offset: int = 0, limite_bytes: int = 65536):
    alvo = resolver(ctx, caminho)
    if not alvo.is_file():
        return {"erro": f"Arquivo não encontrado ou não é arquivo: {alvo}"}
    offset = max(0, int(offset or 0))
    limite = max(1, min(65536, int(limite_bytes or 65536)))
    total = alvo.stat().st_size
    if offset > total:
        return {"erro": f"Offset {offset} ultrapassa o tamanho do arquivo ({total} bytes)."}
    with alvo.open("rb") as arquivo:
        arquivo.seek(offset)
        bruto = arquivo.read(limite)
    # Não cortar uma sequência UTF-8 válida no meio: o próximo bloco começa no byte pendente.
    while bruto:
        try:
            conteudo = bruto.decode("utf-8")
            break
        except UnicodeDecodeError as erro:
            if erro.reason == "unexpected end of data" and erro.end == len(bruto):
                bruto = bruto[:erro.start]
                continue
            conteudo = bruto.decode("utf-8", errors="replace")
            break
    else:
        conteudo = ""
    proximo = offset + len(bruto)
    return {"caminho": str(alvo), "conteudo": conteudo, "offset": offset,
            "proximo_offset": proximo, "total_bytes": total, "fim": proximo >= total}


def _risco_escrever(args, ctx) -> Avaliacao:
    alvo = resolver(ctx, args.get("caminho", ""))
    if caminho_de_sistema(str(alvo)):
        return Avaliacao(CRITICO, f"escrever em pasta do sistema: {alvo}")
    if alvo.exists():
        return Avaliacao(CRITICO, f"sobrescrever {alvo}")
    return Avaliacao(MODERADO, f"criar {alvo}")


@ferramenta(
    "escrever_arquivo",
    "Cria ou substitui um arquivo de texto com o conteúdo informado.",
    {"caminho": texto("Caminho do arquivo"), "conteudo": texto("Texto a gravar")},
    grupo="arquivos", risco=_risco_escrever,
)
def escrever_arquivo(ctx, caminho: str, conteudo: str):
    """Grava primeiro em arquivo temporário e só publica o destino após concluir."""
    alvo = resolver(ctx, caminho)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{alvo.name}.", suffix=".optimus-tmp",
            dir=alvo.parent, delete=False,
        ) as arquivo:
            temporario = arquivo.name
            dados = conteudo.encode("utf-8")
            arquivo.write(dados)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, alvo)
        temporario = None
        return {"mensagem": f"Arquivo salvo em {alvo}", "bytes": len(dados),
                "atomico": True}
    finally:
        if temporario and os.path.exists(temporario):
            try:
                os.unlink(temporario)
            except OSError:
                pass


def _risco_apagar(args, ctx) -> Avaliacao:
    alvo = resolver(ctx, args.get("caminho", ""))
    if caminho_de_sistema(str(alvo)) or alvo == alvo.home() or len(alvo.parts) <= 2:
        return Avaliacao(BLOQUEADO, f"apagar {alvo} danificaria o sistema ou sua pasta pessoal")
    return Avaliacao(CRITICO, f"apagar {alvo}")


@ferramenta(
    "apagar",
    "Apaga um arquivo ou pasta. Sempre pede confirmação ao usuário.",
    {"caminho": texto("Arquivo ou pasta a apagar")},
    grupo="arquivos", risco=_risco_apagar,
)
def apagar(ctx, caminho: str):
    alvo = resolver(ctx, caminho)
    if not alvo.exists():
        return {"erro": f"{alvo} não existe"}
    if alvo.is_dir():
        shutil.rmtree(alvo)
    else:
        alvo.unlink()
    return {"mensagem": f"Apaguei {alvo}"}


def _risco_mover(args, ctx) -> Avaliacao:
    origem = resolver(ctx, args.get("origem", ""))
    destino = resolver(ctx, args.get("destino", ""))
    if caminho_de_sistema(str(origem)) or caminho_de_sistema(str(destino)):
        return Avaliacao(BLOQUEADO, "mover arquivos do sistema")
    if destino.exists() and destino.is_file():
        return Avaliacao(CRITICO, f"substituir {destino}")
    return Avaliacao(CRITICO, f"mover {origem} para {destino}")


@ferramenta(
    "mover",
    "Move ou renomeia um arquivo ou pasta.",
    {"origem": texto("Caminho atual"), "destino": texto("Novo caminho ou pasta")},
    grupo="arquivos", risco=_risco_mover,
)
def mover(ctx, origem: str, destino: str):
    de, para = resolver(ctx, origem), resolver(ctx, destino)
    para.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(de), str(para))
    return {"mensagem": f"Movi {de} para {para}"}


@ferramenta(
    "copiar",
    "Copia um arquivo ou pasta.",
    {"origem": texto("Caminho atual"), "destino": texto("Para onde copiar")},
    grupo="arquivos", risco=lambda a, c: Avaliacao(
        CRITICO if resolver(c, a.get("destino", "")).exists() else MODERADO, "copiar"),
)
def copiar(ctx, origem: str, destino: str):
    de, para = resolver(ctx, origem), resolver(ctx, destino)
    if de.is_dir():
        shutil.copytree(de, para, dirs_exist_ok=True)
    else:
        para.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(de, para)
    return {"mensagem": f"Copiei {de} para {para}"}


@ferramenta(
    "buscar_arquivos",
    "Procura arquivos pelo nome (aceita curingas como *.pdf) dentro de uma pasta.",
    {"padrao": texto("Nome ou padrão, ex.: *.pdf ou relatorio*"),
     "pasta": texto("Onde procurar (padrão: pasta do usuário)"),
     "limite": numero("Máximo de resultados")},
    grupo="arquivos", risco=LIVRE, obrigatorios=["padrao"],
)
def buscar_arquivos(ctx, padrao: str, pasta: str = "~", limite: int = 50):
    raiz = resolver(ctx, pasta)
    if "*" not in padrao and "?" not in padrao:
        padrao = f"*{padrao}*"
    achados = []
    inicio = time.monotonic()
    for atual, pastas, arquivos in os.walk(raiz):
        pastas[:] = [p for p in pastas if not p.startswith(".") and p not in (
            "node_modules", "__pycache__", "AppData", "venv", ".venv")]
        for nome in arquivos:
            if fnmatch.fnmatch(nome.lower(), padrao.lower()):
                achados.append(os.path.join(atual, nome))
                if len(achados) >= limite:
                    return {"total": len(achados), "itens": achados, "cortado": True}
        if time.monotonic() - inicio > 20:
            return {"total": len(achados), "itens": achados, "cortado": True}
    return {"total": len(achados), "itens": achados}
