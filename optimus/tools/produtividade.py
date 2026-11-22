"""Ferramentas de produtividade: hábitos (acompanhamento diário) e timers (contagem regressiva).

São recursos do painel do Optimus (abas Hábitos e Timers): tudo guardado no banco local, no PC
do usuário. Hábitos mostram a sequência de dias seguidos (streak). Timers guardam quanto falta e
quais já venceram, para a interface ou a voz avisarem.
"""

from __future__ import annotations

from optimus.safety import LIVRE, MODERADO
from optimus.tools.base import ferramenta, numero, texto


def _sem_banco(ctx) -> bool:
    return not ctx or not getattr(ctx, "banco", None)


# --------------------------------------------------------------------------- Hábitos
@ferramenta(
    "habito_criar",
    "Cria um hábito para acompanhar todo dia (ex.: 'beber água', 'ler 10 páginas'). Se já "
    "existir um com o mesmo nome, usa o que existe.",
    {"nome": texto("Nome do hábito")}, grupo="produtividade", risco=LIVRE,
)
def habito_criar(ctx, nome: str):
    if _sem_banco(ctx):
        return {"erro": "Sem banco para guardar o hábito."}
    hid = ctx.banco.criar_habito(nome)
    return {"id": hid, "mensagem": f"Hábito '{nome.strip()}' criado."}


@ferramenta(
    "habito_marcar",
    "Marca um hábito como feito hoje (ou desmarca). Aumenta a sequência de dias seguidos.",
    {"id": numero("Id do hábito"),
     "feito": {"type": "boolean", "description": "Feito hoje (padrão: sim). false desmarca."}},
    grupo="produtividade", risco=LIVRE, obrigatorios=["id"],
)
def habito_marcar(ctx, id: int, feito: bool = True):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    if feito:
        novo = ctx.banco.marcar_habito(int(id))
        msg = "Marcado como feito hoje." if novo else "Já estava marcado hoje."
    else:
        ctx.banco.desmarcar_habito(int(id))
        msg = "Desmarcado hoje."
    atual = next((h for h in ctx.banco.listar_habitos() if h["id"] == int(id)), None)
    return {"mensagem": msg, "sequencia": atual["sequencia"] if atual else 0}


@ferramenta(
    "habitos_listar",
    "Lista os hábitos com a sequência de dias seguidos e se já foram feitos hoje.",
    {}, grupo="produtividade", risco=LIVRE,
)
def habitos_listar(ctx):
    if _sem_banco(ctx):
        return {"habitos": []}
    return {"habitos": ctx.banco.listar_habitos()}


@ferramenta(
    "habito_apagar",
    "Apaga um hábito e todo o seu histórico de marcações.",
    {"id": numero("Id do hábito")}, grupo="produtividade", risco=MODERADO, obrigatorios=["id"],
)
def habito_apagar(ctx, id: int):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    ctx.banco.apagar_habito(int(id))
    return {"mensagem": "Hábito apagado."}


# --------------------------------------------------------------------------- Timers
@ferramenta(
    "timer_criar",
    "Cria um timer (contagem regressiva) com nome e duração. Ex.: 'macarrão' por 10 minutos. "
    "A interface/voz avisa quando vencer.",
    {"minutos": numero("Duração em minutos (pode somar com segundos)"),
     "segundos": numero("Segundos extras (opcional)"),
     "nome": texto("Nome do timer (opcional)")},
    grupo="produtividade", risco=LIVRE, obrigatorios=["minutos"],
)
def timer_criar(ctx, minutos: float = 0, segundos: float = 0, nome: str = "Timer"):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    total = round(float(minutos) * 60 + float(segundos))
    if total <= 0:
        return {"erro": "A duração precisa ser maior que zero."}
    tid = ctx.banco.criar_timer(nome, total)
    return {"id": tid, "duracao_seg": total,
            "mensagem": f"Timer '{nome.strip() or 'Timer'}' criado para {total} segundos."}


@ferramenta(
    "timers_listar",
    "Lista os timers ativos com quanto falta (em segundos) e quais já venceram.",
    {"todos": {"type": "boolean", "description": "Incluir os já tocados (padrão: só ativos)"}},
    grupo="produtividade", risco=LIVRE, obrigatorios=[],
)
def timers_listar(ctx, todos: bool = False):
    if _sem_banco(ctx):
        return {"timers": []}
    return {"timers": ctx.banco.listar_timers(apenas_ativos=not todos)}


@ferramenta(
    "timer_cancelar",
    "Cancela (apaga) um timer pelo id.",
    {"id": numero("Id do timer")}, grupo="produtividade", risco=LIVRE, obrigatorios=["id"],
)
def timer_cancelar(ctx, id: int):
    if _sem_banco(ctx):
        return {"erro": "Sem banco."}
    ctx.banco.cancelar_timer(int(id))
    return {"mensagem": "Timer cancelado."}
