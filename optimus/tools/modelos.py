"""Ferramentas de modelos de IA: recomendar o melhor para o hardware e baixá-lo.

O Optimus já detecta o hardware (`optimus.hardware`) e sabe o melhor modelo para ele
(`optimus.modelos`). Estas ferramentas fecham o ciclo que o Kaik pediu: reconhecer a máquina,
recomendar o modelo mais potente que cabe e **baixá-lo** — do PC fraco ao supercomputador.

Correspondem a comandos de voz ("Optimus, qual o melhor modelo pra mim?", "baixe o modelo
recomendado") e a botões do painel. O download passa por confirmação (é pesado: gasta banda e
disco) e só funciona com o Ollama, que é quem roda os modelos locais.
"""

from __future__ import annotations

from optimus import hardware
from optimus import modelos as catalogo
from optimus.engine.ollama import MotorOllama
from optimus.safety import CRITICO, LIVRE, MODERADO
from optimus.tools.base import Contexto, ferramenta, texto


def _motor_ollama(ctx: Contexto) -> MotorOllama:
    url = "http://127.0.0.1:11434"
    if ctx and getattr(ctx, "config", None):
        url = ctx.config.get("motor", "url", url) or url
    return MotorOllama(url)


def _instalados(motor: MotorOllama) -> list[str]:
    """Modelos já baixados no Ollama. Lista vazia se o Ollama não estiver aberto."""
    try:
        return motor.modelos()
    except Exception:
        return []


def _recomendados(ctx: Contexto, motor: MotorOllama | None = None) -> dict:
    hw = hardware.detectar()
    perfil = hardware.escolher_perfil(hw)
    memoria, usou_ram = hardware.memoria_util_gb(hw)
    motor = motor or _motor_ollama(ctx)
    instalados = _instalados(motor)

    atual = ""
    if ctx and getattr(ctx, "config", None):
        atual = ctx.config.get("motor", "modelo", "") or ""

    por_familia = catalogo.melhores_por_familia(hw)
    for item in por_familia:
        rec = item.get("recomendado")
        if rec:
            rec["instalado"] = rec["nome"] in instalados

    faltando = sorted({item["recomendado"]["nome"] for item in por_familia
                       if item.get("recomendado") and not item["recomendado"]["instalado"]})
    return {
        "hardware": hardware.resumo(hw, perfil),
        "memoria_util_gb": round(memoria, 1),
        "usando_ram_sem_placa": usou_ram,
        "modelo_atual": atual,
        "recomendado": perfil.modelo,
        "recomendado_instalado": perfil.modelo in instalados,
        "por_familia": por_familia,
        "nao_instalados": faltando,
        "novidades": catalogo.novidades(),
    }


@ferramenta(
    "modelos_recomendados",
    "Detecta o hardware deste PC e mostra o melhor modelo de IA que cabe nele, por família, "
    "além do modelo em uso e de quais ainda não estão baixados. Não baixa nem muda nada.",
    {}, grupo="sistema", risco=LIVRE,
)
def modelos_recomendados(ctx):
    return _recomendados(ctx)


@ferramenta(
    "modelo_baixar",
    "Baixa um modelo de IA no Ollama pelo nome (ex.: qwen3.5:9b). É um download pesado, que "
    "gasta banda e espaço em disco. Vazio = baixa o modelo recomendado para este hardware.",
    {"nome": texto("Nome do modelo no Ollama. Vazio = o recomendado para este PC.")},
    grupo="sistema", risco=CRITICO, obrigatorios=[],
)
def modelo_baixar(ctx, nome: str = ""):
    motor = _motor_ollama(ctx)
    if not motor.disponivel():
        return {"erro": "Ollama não está respondendo em " + motor.url +
                ". Abra o Ollama e tente de novo."}
    if not nome or not nome.strip():
        nome = hardware.escolher_perfil(hardware.detectar()).modelo
    nome = nome.strip()
    conhecido = any(m.nome == nome and m.confirmado for m in catalogo.CATALOGO)
    estimativa = catalogo.cabe_neste_pc(nome, hardware.detectar())
    ja_tinha = nome in _instalados(motor)
    if ja_tinha:
        return {"baixado": nome, "ja_estava": True, "conhecido": conhecido,
                "mensagem": f"O modelo {nome} já estava instalado no Ollama."}
    try:
        ok = motor.baixar(nome)
    except Exception as erro:
        return {"erro": f"Não consegui falar com o Ollama para baixar {nome}: {erro}"}
    if not ok:
        return {"erro": f"Falha ao baixar {nome}. Confira o nome exato (ollama list / ollama pull), "
                        "espaço em disco e se o Ollama está aberto.",
                "conhecido": conhecido}
    # Verifica se realmente apareceu na lista (evita falso positivo de "baixou")
    instalados = _instalados(motor)
    reconhecido = nome in instalados or any(
        n == nome or n.startswith(nome + ":") or nome.startswith(n.split(":")[0])
        for n in instalados
    )
    if not reconhecido:
        return {
            "erro": f"O Ollama reportou sucesso, mas o modelo '{nome}' ainda não aparece em "
                    f"ollama list. Possíveis causas: download incompleto, falta de disco, "
                    f"ou nome diferente do esperado. Modelos atuais: {instalados[:15]}",
            "baixado_reportado": True,
            "reconhecido": False,
        }
    aviso = ""
    if not conhecido:
        aviso = "Modelo novo ou fora do catálogo: baixado mesmo assim. "
        if estimativa.get("memoria_gb") and not estimativa.get("cabe"):
            aviso += (f"Ele deve precisar de uns {estimativa['memoria_gb']} GB e este PC tem "
                      f"{estimativa['memoria_util_gb']} GB úteis: pode ficar muito lento. ")
        aviso += "Use modelo_avaliar para testar."
    return {
        "baixado": nome,
        "reconhecido": True,
        "conhecido": conhecido,
        "estimativa": estimativa,
        "aviso": aviso,
        "mensagem": f"Modelo {nome} baixado e reconhecido pelo Ollama.",
    }


@ferramenta(
    "modelo_usar",
    "Passa a usar o modelo indicado (grava na configuração). Vazio = o recomendado para este "
    "hardware. Não baixa: use modelo_baixar antes se ele ainda não estiver instalado.",
    {"nome": texto("Nome do modelo no Ollama. Vazio = o recomendado para este PC.")},
    grupo="sistema", risco=MODERADO, obrigatorios=[],
)
def modelo_usar(ctx, nome: str = ""):
    if not ctx or not getattr(ctx, "config", None):
        return {"erro": "Sem configuração para gravar o modelo."}
    hw = hardware.detectar()
    if not nome or not nome.strip():
        nome = hardware.escolher_perfil(hw).modelo
    nome = nome.strip()
    catalogo.aceitar_upgrade(ctx.config, hw, nome)
    return {"usando": nome}


@ferramenta(
    "modelo_cabe",
    "Diz se um modelo qualquer de IA (até lançamentos novos, fora do catálogo e sem avaliação) "
    "cabe neste PC: estima a memória pelo tamanho e pela quantização e lê as capacidades "
    "(ferramentas, imagem, raciocínio) no Ollama quando ele já está baixado.",
    {"nome": texto("Nome do modelo, ex.: qwen3.8:27b ou hf.co/usuario/Modelo-7B-GGUF:Q4_K_M")},
    grupo="sistema", risco=LIVRE,
)
def modelo_cabe(ctx, nome: str):
    info = _motor_ollama(ctx).info(nome.strip())
    return catalogo.cabe_neste_pc(nome.strip(), hardware.detectar(), info)


@ferramenta(
    "modelo_avaliar",
    "Faz um teste rápido de um modelo neste PC (velocidade, português e uma conta) e dá uma "
    "nota de 0 a 10. Serve para modelos novos que ainda não têm avaliação pública.",
    {"nome": texto("Nome do modelo instalado. Vazio = o modelo em uso.")},
    grupo="sistema", risco=LIVRE, obrigatorios=[],
)
def modelo_avaliar(ctx, nome: str = ""):
    if not nome or not nome.strip():
        nome = (ctx.config.get("motor", "modelo", "") if ctx and getattr(ctx, "config", None)
                else "") or hardware.escolher_perfil(hardware.detectar()).modelo
    return catalogo.avaliar(_motor_ollama(ctx), nome.strip())


@ferramenta(
    "modelos_catalogo_atualizar",
    "Baixa do GitHub a lista mais nova de modelos de IA abertos (novos lançamentos de Google, "
    "Meta, Alibaba, DeepSeek, NVIDIA, Mistral...), sem precisar atualizar o Optimus.",
    {}, grupo="sistema", risco=LIVRE,
)
def modelos_catalogo_atualizar(ctx):
    repo = ctx.config.get("atualizacao", "github", "") if ctx and getattr(ctx, "config", None) \
        else ""
    return catalogo.atualizar_catalogo(repo)
