"""Arquivos e pastas."""

from __future__ import annotations

import fnmatch
import os
import shutil
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
    "Lê um arquivo de texto (código, notas, configurações, CSV...).",
    {"caminho": texto("Caminho do arquivo")},
    grupo="arquivos",
)
def ler_arquivo(ctx, caminho: str):
    alvo = resolver(ctx, caminho)
    if alvo.stat().st_size > 2_000_000:
        return {"erro": "Arquivo grande demais para ler inteiro (mais de 2 MB)."}
    conteudo = alvo.read_text(encoding="utf-8", errors="replace")
    return {"caminho": str(alvo), "conteudo": conteudo[:20000],
            "cortado": len(conteudo) > 20000}


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
    alvo = resolver(ctx, caminho)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(conteudo, encoding="utf-8")
    return {"mensagem": f"Arquivo salvo em {alvo}", "bytes": len(conteudo.encode())}


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
