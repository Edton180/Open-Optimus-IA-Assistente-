"""API da tela Estúdio (/api/estudio/...). Usa as mesmas ferramentas do chat, então as regras
(consentimento para clonar, validação, fila) são as mesmas em todo lugar.

Rotas:
  GET  vozes | tarefas | historico | pronuncia | diagnostico
  GET  arquivo?caminho=...        (só arquivos das pastas do estúdio)
  POST enviar (multipart: arquivo) → caminho salvo em estudio/entradas
  POST falar | criar-voz | clonar (multipart: nome, consentimento, arquivo)
  POST dublar | legendar | audiolivro | historia | separar | transcrever | verificar
  POST tarefas/<id>/cancelar | tarefas/<id>/repetir | historico/<id>/favorito
  DELETE historico[/<id>]?arquivos=1&favoritos=1 (apaga um item ou o histórico)
  POST pronuncia {escrito, falado}   DELETE pronuncia/<escrito>   DELETE vozes/<voz>
  GET  modelos | receitas            POST modelos/<id>/instalar | modelos/<id>/remover
  POST desempenho {escolha} | receitas {nome, acao, opcoes} | receitas/<nome>/rodar {arquivo}
  POST observar {pasta, receita}     DELETE receitas/<nome> | observar?pasta=...
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from optimus.tools.base import Contexto

LIMITE_ENVIO = 2 * 1024 * 1024 * 1024  # 2 GB, enviado direto para o disco
LIMITE_FORMULARIO = 200 * 1024 * 1024  # formulários (clonar uma voz) ficam na memória

_ACOES = {  # rota → ferramenta (os campos do JSON viram os argumentos)
    "falar": "estudio_falar", "criar-voz": "estudio_criar_voz", "dublar": "estudio_dublar",
    "legendar": "estudio_legendar", "audiolivro": "estudio_audiolivro",
    "historia": "estudio_historia", "separar": "estudio_separar_voz",
    "transcrever": "estudio_transcrever", "verificar": "estudio_verificar_ia",
    "quem-fala": "estudio_quem_fala", "ajustar-voz": "estudio_ajustar_voz",
    "converter": "estudio_converter_voz",
}


class _Agente:
    """O suficiente de um agente para as ferramentas acharem o modelo de IA (tradução)."""

    def __init__(self, optimus):
        self.motor = optimus.motor
        self._optimus = optimus

    def modelo_principal(self) -> str:
        return self._optimus.modelo_atual()


def _contexto(optimus) -> Contexto:
    pasta = optimus.config.get("agente", "pasta_trabalho", "") or str(Path.home())
    return Contexto(config=optimus.config, banco=getattr(optimus, "banco", None),
                    pasta_trabalho=Path(pasta).expanduser(), agente=_Agente(optimus))


def pastas_permitidas(config) -> list[Path]:
    from optimus.estudio import pasta_estudio, pasta_saidas

    return [pasta_saidas(config).resolve(), pasta_estudio().resolve()]


def arquivo_permitido(caminho: str, config) -> Path | None:
    """Só serve arquivos que o estúdio criou ou recebeu: nada de ler o disco todo."""
    try:
        alvo = Path(caminho).expanduser().resolve()
    except (OSError, ValueError):
        return None
    if not alvo.is_file():
        return None
    for pasta in pastas_permitidas(config):
        if alvo == pasta or pasta in alvo.parents:
            return alvo
    return None


def _nome_seguro(nome: str) -> str:
    nome = Path(nome or "arquivo").name
    nome = re.sub(r"[^\w.\- ]+", "_", nome).strip(" .") or "arquivo"
    return nome[:120]


def salvar_envio(nome: str, dados: bytes) -> Path:
    from optimus.estudio import pasta_estudio

    pasta = pasta_estudio() / "entradas"
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / f"{time.strftime('%Y%m%d-%H%M%S')}-{_nome_seguro(nome)}"
    alvo.write_bytes(dados)
    return alvo


def receber_envio(nome: str, fluxo, tamanho: int) -> Path:
    """Copia o corpo do pedido para estudio/entradas em pedaços de 1 MB."""
    from optimus.estudio import pasta_estudio
    from optimus.estudio.audio import ErroEstudio

    pasta = pasta_estudio() / "entradas"
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / f"{time.strftime('%Y%m%d-%H%M%S')}-{_nome_seguro(nome)}"
    restante = tamanho
    with open(alvo, "wb") as f:
        while restante > 0:
            pedaco = fluxo.read(min(1024 * 1024, restante))
            if not pedaco:
                break
            f.write(pedaco)
            restante -= len(pedaco)
    if restante > 0:
        alvo.unlink(missing_ok=True)
        raise ErroEstudio("O envio foi interrompido.")
    return alvo


def _ferramenta(nome: str, argumentos: dict, ctx) -> dict:
    from optimus.tools.base import registradas

    ferramenta = registradas()[nome]
    aceitos = set(ferramenta.parametros)
    limpos = {k: v for k, v in argumentos.items() if k in aceitos and v not in (None, "")}
    faltam = [o for o in ferramenta.obrigatorios if o not in limpos]
    if faltam:
        return {"erro": "Faltou: " + ", ".join(faltam)}
    resultado = ferramenta.funcao(ctx, **limpos)
    return resultado if isinstance(resultado, dict) else {"resultado": resultado}


def _verdade(valor: Any) -> bool:
    return str(valor).strip().lower() in ("1", "true", "sim", "on", "yes")


def atender(metodo: str, partes: list[str], consulta: dict, tipo: str, corpo: bytes,
            optimus) -> tuple[int, Any]:
    """Devolve (status, dados). `dados` é um dict (JSON) ou um Path (arquivo a enviar)."""
    from optimus.estudio import historico, pronuncia, vozes
    from optimus.estudio.audio import ErroEstudio
    from optimus.estudio.fila import fila
    from optimus.web.openai_audio import multipart

    config = optimus.config
    recurso = partes[0] if partes else ""
    ident = "/".join(partes[1:])
    ctx = _contexto(optimus)
    dados: dict[str, Any] = {}
    if metodo == "POST" and corpo:
        if tipo.startswith("multipart/"):
            campos = multipart(tipo, corpo)
            for campo, (nome_arq, conteudo) in campos.items():
                if nome_arq:
                    dados[campo] = str(salvar_envio(nome_arq, conteudo))
                else:
                    dados[campo] = conteudo.decode("utf-8", "replace")
        else:
            try:
                dados = json.loads(corpo or b"{}")
            except json.JSONDecodeError:
                return 400, {"erro": "JSON inválido"}
    try:
        if metodo == "GET":
            if recurso == "vozes":
                return 200, {"vozes": [p.para_dict() for p in vozes.listar()],
                             "declaracao": vozes.DECLARACAO}
            if recurso == "tarefas":
                return 200, {"tarefas": [t.para_dict() for t in fila().listar(50)]}
            if recurso == "historico":
                busca = (consulta.get("busca") or [""])[0]
                return 200, {"itens": historico(busca, _verdade((consulta.get("favoritos")
                                                                  or [""])[0]))}
            if recurso == "pronuncia":
                return 200, {"regras": pronuncia.listar()}
            if recurso == "diagnostico":
                from optimus.estudio.cli import diagnostico

                return 200, {"itens": [{"nome": n, "ok": ok, "dica": d}
                                       for n, ok, d in diagnostico()]}
            if recurso == "idiomas":
                from optimus.estudio import idiomas

                return 200, {"idiomas": [{"codigo": i.codigo, "nome": i.nome}
                                         for i in idiomas.todos()]}
            if recurso == "modelos":
                from optimus.estudio import desempenho, modelos

                atual = desempenho.atual(config)
                return 200, {"modelos": modelos.listar(),
                             "desempenho": str(config.get("estudio", "desempenho", "auto")),
                             "atual": atual.para_dict(), "recomendada": desempenho.recomendar()}
            if recurso == "receitas":
                from optimus.estudio import automacao

                return 200, {"receitas": [r.para_dict() for r in automacao.receitas()],
                             "observadas": automacao.observadas(),
                             "acoes": sorted(automacao.ACOES_PERMITIDAS)}
            if recurso == "arquivo":
                alvo = arquivo_permitido((consulta.get("caminho") or [""])[0], config)
                return (200, alvo) if alvo else (404, {"erro": "arquivo não encontrado"})
        if metodo == "DELETE":
            if recurso == "historico":
                from optimus.estudio import apagar_historico

                arquivos = _verdade((consulta.get("arquivos") or [""])[0])
                if ident:
                    return 200, {"removidos": apagar_historico(ident, apagar_arquivos=arquivos)}
                manter = not _verdade((consulta.get("favoritos") or [""])[0])
                return 200, {"removidos": apagar_historico(tudo=True, manter_favoritos=manter,
                                                           apagar_arquivos=arquivos)}
            if recurso == "pronuncia" and ident:
                return 200, {"removido": pronuncia.remover(ident)}
            if recurso == "vozes" and ident:
                return 200, _ferramenta("estudio_apagar_voz", {"voz": ident}, ctx)
            if recurso == "receitas" and ident:
                from optimus.estudio import automacao

                return 200, {"removida": automacao.apagar_receita(ident)}
            if recurso == "observar":
                from optimus.estudio import automacao

                return 200, {"parou": automacao.parar_de_observar(
                    (consulta.get("pasta") or [""])[0])}
        if metodo == "POST":
            if recurso == "enviar":
                if not dados.get("arquivo"):
                    return 400, {"erro": "Mande o arquivo no campo 'arquivo'."}
                return 200, {"caminho": dados["arquivo"]}
            if recurso == "clonar":
                if not _verdade(dados.get("consentimento")):
                    return 400, {"erro": vozes.DECLARACAO}
                nome = str(dados.get("nome", "") or "").strip()
                edton = nome.casefold() in ("edton braz", "edton braz — voz personalizada",
                                             "edton braz - voz personalizada")
                p = vozes.clonar(nome, dados.get("arquivo", ""), True,
                                 dados.get("idioma") or "pt-BR",
                                 genero="masculina" if edton else "",
                                 descricao="Voz pessoal Edton Braz, clonada de amostra autorizada"
                                 if edton else "")
                return 200, {"voz": p.para_dict()}
            if recurso == "pronuncia":
                pronuncia.adicionar(dados.get("escrito", ""), dados.get("falado", ""))
                return 200, {"regras": pronuncia.listar()}
            if recurso == "tarefas" and len(partes) == 3:
                tarefa = fila().obter(partes[1])
                if tarefa is None:
                    return 404, {"erro": "tarefa não encontrada"}
                if partes[2] == "cancelar":
                    return 200, {"ok": fila().cancelar(tarefa.id)}
                if partes[2] == "repetir":
                    nova = fila().repetir(tarefa.id)
                    return 200, {"tarefa": nova.id if nova else None}
            if recurso == "modelos" and len(partes) == 2 and partes[1] == "instalar-todos":
                return 200, _ferramenta("estudio_instalar_todos_modelos", {}, ctx)
            if recurso == "modelos" and len(partes) == 3:
                from optimus.estudio import modelos

                if partes[2] == "remover":
                    return 200, {"modelo": modelos.remover(partes[1])}
                if partes[2] == "instalar":
                    return 200, _ferramenta("estudio_instalar_modelo", {"modelo": partes[1]}, ctx)
            if recurso == "desempenho":
                from optimus.estudio import desempenho

                return 200, {"atual": desempenho.escolher(config, str(dados.get("escolha", "auto"))
                                                          ).para_dict()}
            if recurso == "receitas":
                from optimus.estudio import automacao

                if len(partes) == 3 and partes[2] == "rodar":
                    resultado = automacao.aplicar(partes[1], dados.get("arquivo", ""), config)
                    return (400 if resultado.get("erro") else 200), resultado
                opcoes = dados.get("opcoes") or {}
                if isinstance(opcoes, str):
                    from optimus.tools.estudio import _pares

                    opcoes = _pares(opcoes)
                r = automacao.salvar_receita(dados.get("nome", ""), dados.get("acao", ""),
                                             opcoes, dados.get("descricao", ""))
                return 200, {"receita": r.para_dict()}
            if recurso == "observar":
                from optimus.estudio import automacao

                regra = automacao.observar(dados.get("pasta", ""), dados.get("receita", ""))
                automacao.iniciar_se_preciso(config)
                return 200, {"observando": regra}
            if recurso == "historico" and len(partes) == 3 and partes[2] == "favorito":
                from optimus.estudio import favoritar

                return 200, {"ok": favoritar(partes[1])}
            if recurso in _ACOES:
                if recurso == "falar":
                    dados.pop("arquivo", None)  # pela tela, sempre salva na pasta de saídas
                for chave in ("voz_original", "consentimento", "separar_falantes", "falantes"):
                    if chave in dados:
                        dados[chave] = _verdade(dados[chave])
                if recurso == "dublar" and dados.get("voz_original") \
                        and not dados.get("consentimento"):
                    return 400, {"erro": vozes.DECLARACAO}
                resultado = _ferramenta(_ACOES[recurso], dados, ctx)
                return (400 if resultado.get("erro") else 200), resultado
    except (ErroEstudio, ValueError, KeyError) as erro:
        return 400, {"erro": str(erro)}
    return 404, {"erro": "rota do estúdio desconhecida"}
