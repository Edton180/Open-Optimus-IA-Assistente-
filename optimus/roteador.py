"""Roteamento dos pedidos: o que resolver na hora, o que buscar antes e quais ferramentas
mostrar ao modelo.

Por que isso existe: mandar todas as ~50 ferramentas em cada pedido gasta milhares de
tokens. Num PC fraco (CPU de 2 núcleos, contexto de 4096 tokens) isso deixava cada resposta
com minutos de espera e, pior, estourava o contexto: o modelo pequeno passava a ler a
própria instrução de sistema como pedido e criava lembretes sozinho. Agora cada pedido
recebe só as ferramentas da sua intenção (nenhuma, numa conversa comum).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


# (regex sobre o texto normalizado, ferramentas). A ordem define a prioridade.
INTENCOES: list[tuple[str, list[str]]] = [
    (r"\b(lembre(-| )?me|me lembr|lembrete|alarme|despert|timer|cronometro|avise[- ]me|"
     r"me avis|agend)", ["criar_lembrete", "listar_lembretes", "cancelar_lembretes"]),
    (r"\b(lembre que|guarde|memoriz|anote que|meu nome e|eu (gosto|moro|trabalho|sou|tenho)|"
     r"o que (voce )?sabe (sobre|de) mim|recorda|esqueca)", ["lembrar", "recordar"]),
    (r"\b(aprend|estud|base de conhecimento)", ["aprender", "consultar_conhecimento"]),
    (r"\b(pesquis|procur[ea] na|busqu|internet|google|site|pagina|link|https?://|preco|"
     r"cotacao|quem (e|foi)|o que (e|foi|sao)|quando (e|foi)|ultimas|atual)",
     ["pesquisar_web", "ler_pagina", "noticias"]),
    (r"\bnoticia", ["noticias", "pesquisar_web"]),
    (r"\b(clima|previsao|vai chover|temperatura (em|de|hoje|amanha|la fora))", ["clima"]),
    (r"\b(volume|som|mudo|silenci|brilho|musica|tocar|toque|pausa|pause|proxima|anterior|"
     r"spotify)", ["volume", "brilho", "midia"]),
    (r"\b(luz|luzes|lampada|tomada|ar[- ]condicionado|\bar\b|tv|televis|casa|camera|"
     r"bluetooth|wi-?fi|sensor|persiana|cortina|portao|fechadura|alexa|barulho|frio|calor|"
     r"abafad|umidade|ventilador|aspirador)",
     ["casa_relatorio", "casa_falar", "casa_controlar", "casa_dispositivos", "casa_diagnostico",
      "casa_varios", "camera_foto", "cameras_listar", "bluetooth_procurar", "bluetooth_conectar",
      "rede_local", "alexa_anunciar"]),
    (r"\b(outro pc|outro computador|pc da|computador da|liga(r)? o (pc|computador)|wake|ssh|"
     r"servidor)", ["pc_listar", "pc_ligar", "pc_comando"]),
    (r"\b(codigo|programa(r|cao)?|script|bug|teste|git|commit|branch|docker|container|"
     r"projeto|funcao|python|javascript|typescript|html|css|app|aplicativo|refator|compil)",
     ["buscar_no_codigo", "ler_codigo", "editar_arquivo", "escrever_arquivo", "rodar_testes",
      "git", "docker", "executar_comando", "listar_pasta", "delegar"]),
    (r"\b(arquivo|pasta|diretorio|documento|downloads|desktop|area de trabalho|planilha|pdf|"
     r"ler o|leia|escrev|salv|cri[ea] (um|uma|o|a)? ?(arquivo|pasta|nota)|apag|delet|exclu|"
     r"mov[ae]|copi[ae]|renome|organiz)",
     ["listar_pasta", "ler_arquivo", "buscar_arquivos", "escrever_arquivo", "apagar", "mover",
      "copiar", "organizar_pasta"]),
    (r"\b(pc|computador|notebook|cpu|processador|ram|memoria|disco|processo|desempenho|"
     r"bateria|lento|travando|uso)", ["desempenho", "info_sistema", "listar_processos"]),
    (r"\b(abr[ae]|abrir|inici[ae]|execut[ae]|fech[ae]|fechar|encerr|mat[ae] o)",
     ["abrir", "encerrar_processo", "executar_comando"]),
    (r"\b(deslig|reinici|suspend|hibern|bloque(ia|ar) (a tela|o pc))", ["energia"]),
    (r"\b(comando|terminal|powershell|bash|instal)", ["executar_comando"]),
    (r"\b(digit|tecla|clique|clicar|mouse|print|captura de tela|tela|area de transferencia|"
     r"copiad)", ["captura_tela", "digitar", "teclas", "clicar", "area_transferencia"]),
    (r"(mud|troc|troqu|qua(l|is)|list|usar|use|outra).{0,25}\bvoz", ["trocar_voz", "listar_vozes"]),
    (r"(\d\s*[-+*/x^]\s*\d|calcul|quanto (e|da|sao)|porcent|raiz)", ["calcular"]),
    (r"\b(que horas|hora|data de hoje|que dia)", ["data_hora"]),
    (r"\b(imagem|desenh|ilustra|arte de|foto de|logo|wallpaper|papel de parede)",
     ["gerar_imagem"]),
    (r"\b(pesquisa profunda|a fundo|audit|seguranca do|vulnerab|devops|especialista)",
     ["delegar"]),
]


def tamanho_modelo(nome: str) -> float:
    """Bilhões de parâmetros pelo nome (qwen3.5:2b → 2.0). 0 se não souber."""
    achado = re.search(r"(\d+(?:\.\d+)?)\s*b\b", (nome or "").lower())
    return float(achado.group(1)) if achado else 0.0


def selecionar_ferramentas(texto: str, disponiveis: dict[str, Any], pequeno: bool = False,
                           extras: list[str] | None = None) -> dict[str, Any]:
    """Escolhe as ferramentas pela intenção do pedido. Conversa comum: nenhuma."""
    t = normal(texto)
    escolhidas: list[str] = []
    for padrao, nomes in INTENCOES:
        if re.search(padrao, t):
            escolhidas += [n for n in nomes if n in disponiveis and n not in escolhidas]
    for nome in extras or []:
        if nome in disponiveis and nome not in escolhidas:
            escolhidas.append(nome)
    limite = 6 if pequeno else 16
    return {n: disponiveis[n] for n in escolhidas[:limite]}


# Pedidos que buscamos ANTES de chamar o modelo (bom para modelos pequenos, que erram
# chamadas de ferramenta): o resultado vai junto com a pergunta.
_PRE = [
    (r"^(pesquise|pesquisa|pesquisar|procure|busque|busca|google)( na internet| na web| no google)?"
     r"( sobre| por| o que e| quem e)? (?P<q>.+)", "pesquisar_web", "consulta"),
    (r"^(quais (sao )?as )?(ultimas )?noticias( de hoje)?( sobre| de| do| da)? ?(?P<q>.*)",
     "noticias", "assunto"),
    (r"^(como (esta|vai) o )?(clima|tempo|previsao do tempo)( hoje| amanha| agora)? "
     r"(em|para|de|no|na) (?P<q>.+)", "clima", "cidade"),
    (r"^(como (esta|anda) (o )?(meu )?(pc|computador|notebook)|uso de (cpu|ram|memoria)|"
     r"desempenho do (pc|computador))(?P<q>)", "desempenho", ""),
    (r"^(quais (sao )?(os )?(meus )?lembretes|listar? (os )?lembretes|meus lembretes)(?P<q>)",
     "listar_lembretes", ""),
]


def pre_execucao(texto: str) -> tuple[str, dict[str, Any]] | None:
    t = normal(texto).rstrip("?!. ")
    t = re.sub(r"^(optimus|ei optimus|ok optimus|ola optimus)[, ]*", "", t)
    for padrao, ferramenta, chave in _PRE:
        achado = re.match(padrao, t)
        if achado:
            consulta = (achado.group("q") or "").strip()
            if chave == "assunto":
                return ferramenta, {"assunto": consulta or "Brasil"}
            if chave:
                if not consulta:
                    return None
                return ferramenta, {chave: consulta}
            return ferramenta, {}
    return None


_SITES = {"youtube": "https://www.youtube.com", "google": "https://www.google.com",
          "gmail": "https://mail.google.com", "whatsapp": "https://web.whatsapp.com",
          "instagram": "https://www.instagram.com", "github": "https://github.com",
          "netflix": "https://www.netflix.com", "spotify": "https://open.spotify.com",
          "chatgpt": "https://chatgpt.com", "mapas": "https://maps.google.com",
          "facebook": "https://www.facebook.com", "tiktok": "https://www.tiktok.com",
          "x": "https://x.com", "twitter": "https://x.com"}


def roteador_rapido(texto: str) -> tuple[str, dict[str, Any]] | None:
    """Pedidos óbvios resolvidos sem o modelo. Devolve (ferramenta, argumentos)."""
    t = normal(texto).rstrip("?!. ")
    t = re.sub(r"^(optimus|ei optimus|ok optimus)[, ]*", "", t)
    if re.fullmatch(r"(que horas sao|que hora e|me diz as horas|horas)( agora)?", t):
        return "data_hora", {}
    if re.fullmatch(r"(que dia e hoje|qual a data de hoje|que dia e hoje\??)", t):
        return "data_hora", {}
    achado = re.fullmatch(r"(abr[ae]|abrir)( o| a)? (\w+)", t)
    if achado and achado.group(3) in _SITES:
        return "abrir", {"alvo": _SITES[achado.group(3)]}
    achado = re.search(r"(mud[ae]|troc[ae]|troqu[ea]|us[ae]|usar|ativ[ae]|coloc[ae]|coloqu[ea])"
                       r"( para| pra)?( a)? voz"
                       r"( para| pra| da| de)?( a| o)? (?P<voz>[\w-]+)", t)
    if achado:
        return "trocar_voz", {"voz": achado.group("voz")}
    if re.fullmatch(r"(cancel[ae]r?|apag[ae]r?|remov[ae]r?|exclu[ia]r?|limp[ae]r?)( todos)?"
                    r"( os)?( meus)? (lembretes|alarmes)( todos)?", t):
        return "cancelar_lembretes", {}
    achado = re.fullmatch(r"(aumenta|abaixa|baixa|diminui)( o)? volume", t)
    if achado:
        return "volume", {"acao": "aumentar" if achado.group(1) == "aumenta" else "baixar"}
    if re.fullmatch(r"(pausa|pause|para a musica|tocar|toca|play|proxima( musica)?|"
                    r"musica anterior|volta a musica)", t):
        acao = ("pausar" if t.startswith("pau") or t.startswith("para") else
                "proxima" if t.startswith("prox") else
                "anterior" if "anterior" in t or t.startswith("volta") else "tocar")
        return "midia", {"acao": acao}
    return None
