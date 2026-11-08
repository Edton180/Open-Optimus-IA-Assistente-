"""Modo demonstração: um motor simples, sem modelo de IA, para testar a instalação.

Ele reconhece alguns pedidos por palavras-chave e chama as ferramentas de verdade
(as ferramentas executam de fato). Serve para ver a interface, a voz e as confirmações
funcionando antes de baixar um modelo. Não é inteligente: troque para o Ollama depois.
"""

from __future__ import annotations

import json
import re
import unicodedata

from optimus.engine.base import ChamadaFerramenta, Motor, Resposta


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _caminho(_texto: str) -> str:
    """Pega o caminho do texto original (mantém maiúsculas e barras do Windows)."""
    achados = re.findall(r"(?:[A-Za-z]:)?[\w\-./\\~:]+\.\w+", MotorDemo._original)
    return achados[-1] if achados else "arquivo.txt"


_REGRAS = [
    (r"(hardware|meu pc|computador|cpu|memoria|ram)", "info_sistema", lambda t: {}),
    (r"(processo|programas abertos)", "listar_processos", lambda t: {"limite": 8}),
    (r"(que horas|data de hoje|dia e hoje)", "data_hora", lambda t: {}),
    (r"(lembre|lembrete|me avise)", "criar_lembrete",
     lambda t: {"texto": re.sub(r"^.*?(lembre(-me)? de|lembrete( de| para)?|me avise( de| para)?)\s*|\s*(em|daqui a) \d+\s*min\w*", "", t).strip() or t, "minutos": int((re.findall(r"(\d+)\s*min", t) or ["10"])[0])}),
    (r"(liste|listar|mostre).*(arquivos|pasta)", "listar_pasta",
     lambda t: {"caminho": "~/Downloads" if "download" in t else
                "~/Documentos" if "document" in t else "."}),
    (r"(apague|apagar|delete|exclua).*", "apagar",
     lambda t: {"caminho": _caminho(t)}),
    (r"(abra|abrir).*(site|youtube|google|http)", "abrir",
     lambda t: {"alvo": "https://www.youtube.com" if "youtube" in t else "https://www.google.com"}),
    (r"(pesquise|procure|busque|pesquisar)", "pesquisar_web",
     lambda t: {"consulta": re.sub(r"^.*?(pesquise|procure|busque|pesquisar)( sobre)?", "", t)
                .strip() or t}),
    (r"(calcule|quanto e)", "calcular",
     lambda t: {"expressao": re.sub(r"[^0-9+\-*/(). ]", "", t).strip() or "2+2"}),
]


class MotorDemo(Motor):
    nome = "demo"
    _original = ""

    def conversar(self, mensagens, modelo, ferramentas=None, opcoes=None) -> Resposta:
        ultima = mensagens[-1]
        nomes = {f["function"]["name"] for f in (ferramentas or [])}
        if ultima["role"] == "tool":
            return Resposta(texto=self._resumir(ultima.get("content", "")), modelo="demo")
        texto = _normal(ultima.get("content", ""))
        MotorDemo._original = ultima.get("content", "")
        for padrao, ferramenta, argumentos in _REGRAS:
            if ferramenta in nomes and re.search(padrao, texto):
                return Resposta(chamadas=[ChamadaFerramenta(ferramenta, argumentos(texto))],
                                modelo="demo")
        if re.search(r"^(oi|ola|bom dia|boa tarde|boa noite|e ai)", texto):
            return Resposta(texto="Olá! Sou o Optimus. Estou no modo demonstração: consigo "
                                  "mostrar o sistema, listar arquivos, criar lembretes e abrir "
                                  "sites. Para conversar de verdade, instale um modelo com "
                                  "`optimus instalar-modelo`.", modelo="demo")
        return Resposta(texto="Estou no modo demonstração, sem modelo de IA carregado. "
                              "Rode `optimus instalar-modelo` para eu ficar inteligente.",
                        modelo="demo")

    def _resumir(self, conteudo: str) -> str:
        try:
            dados = json.loads(conteudo)
        except json.JSONDecodeError:
            return conteudo[:600]
        if isinstance(dados, dict) and "erro" in dados:
            return f"Não deu certo: {dados['erro']}"
        if isinstance(dados, dict) and "cpu" in dados:
            return (f"Seu PC tem {dados['cpu']} com {dados.get('nucleos')} núcleos, "
                    f"{dados.get('ram_total_gb')} GB de RAM ({dados.get('ram_uso_pct')}% em uso). "
                    f"Perfil escolhido: {dados.get('perfil')}, modelo {dados.get('modelo')}.")
        if isinstance(dados, dict) and "itens" in dados:
            itens = dados["itens"][:8]
            nomes = ", ".join(i.get("nome", str(i)) if isinstance(i, dict) else str(i)
                              for i in itens)
            return f"Encontrei {dados.get('total', len(itens))} itens: {nomes}."
        if isinstance(dados, dict) and "mensagem" in dados:
            return str(dados["mensagem"])
        return json.dumps(dados, ensure_ascii=False)[:600]

    def disponivel(self) -> bool:
        return True

    def modelos(self) -> list[str]:
        return ["demo"]
