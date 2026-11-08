"""O agente: conversa, decide quais ferramentas usar, pede confirmação e responde.

Fluxo de cada pedido:
1. Roteador rápido: pedidos óbvios ("que horas são", "abre o YouTube") são resolvidos
   na hora, sem chamar o modelo. Isso deixa PCs fracos respondendo instantaneamente.
2. Guarda de recursos: se a RAM livre está baixa, ou é uma pergunta curta por voz, usa o
   modelo rápido; senão, o principal.
3. Ciclo de ferramentas (estilo ReAct): o modelo pede ferramentas, o Optimus avalia o
   risco, pergunta ao usuário quando precisa, executa e devolve o resultado ao modelo,
   até ele dar a resposta final ou chegar ao limite de passos.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

import psutil

from optimus.engine.base import ChamadaFerramenta, ErroMotor, Motor, extrair_chamadas_do_texto
from optimus.safety import NOMES_NIVEL, Auditoria, Avaliacao, precisa_confirmar
from optimus.tools import Contexto, Ferramenta, ferramentas_ativas
from optimus.tools.base import sistema

Confirmar = Callable[[ChamadaFerramenta, Avaliacao], bool]
Evento = Callable[[dict[str, Any]], None]

_INSTRUCOES_FERRAMENTAS = (
    "\n\nPara usar uma ferramenta, chame-a pela API de ferramentas. Se não conseguir, escreva "
    "apenas: <tool_call>{\"name\": \"nome_da_ferramenta\", \"arguments\": {...}}</tool_call>. "
    "Ferramentas disponíveis: {lista}."
)

_INSTRUCOES_AUTONOMO = (
    "\n\nMODO AUTÔNOMO: quando receber um objetivo, faça um plano curto, execute cada passo "
    "com as ferramentas, confira o resultado e continue até concluir, sem pedir permissão para "
    "passos seguros. Ações críticas serão confirmadas pelo próprio sistema. No fim, diga o que "
    "foi feito e o que ficou pendente."
)


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


_SITES = {"youtube": "https://www.youtube.com", "google": "https://www.google.com",
          "gmail": "https://mail.google.com", "whatsapp": "https://web.whatsapp.com",
          "instagram": "https://www.instagram.com", "github": "https://github.com",
          "netflix": "https://www.netflix.com", "spotify": "https://open.spotify.com",
          "chatgpt": "https://chatgpt.com", "mapas": "https://maps.google.com"}


def roteador_rapido(texto: str) -> tuple[str, dict[str, Any]] | None:
    """Pedidos óbvios que não precisam do modelo. Devolve (ferramenta, argumentos)."""
    t = _normal(texto).rstrip("?!. ")
    t = re.sub(r"^(optimus|ei optimus|ok optimus)[, ]*", "", t)
    if re.fullmatch(r"(que horas sao|que hora e|me diz as horas|horas)( agora)?", t):
        return "data_hora", {}
    if re.fullmatch(r"(que dia e hoje|qual a data de hoje|que dia e hoje\??)", t):
        return "data_hora", {}
    achado = re.fullmatch(r"(abr[ae]|abrir)( o| a)? (\w+)", t)
    if achado and achado.group(3) in _SITES:
        return "abrir", {"alvo": _SITES[achado.group(3)]}
    return None


@dataclass
class Agente:
    config: Any
    motor: Motor
    banco: Any = None
    perfil: Any = None
    confirmar: Confirmar | None = None
    ao_evento: Evento | None = None
    auditoria: Auditoria | None = None
    ferramentas: dict[str, Ferramenta] = field(default_factory=dict)

    def __post_init__(self):
        if not self.ferramentas:
            self.ferramentas = ferramentas_ativas(self.config)
        pasta = self.config.get("agente", "pasta_trabalho") or ""
        from pathlib import Path

        self.contexto = Contexto(config=self.config, banco=self.banco, perfil=self.perfil,
                                 pasta_trabalho=Path(pasta).expanduser() if pasta else Path.home())

    # Utilidades
    def _emitir(self, tipo: str, **dados) -> None:
        if self.ao_evento:
            try:
                self.ao_evento({"tipo": tipo, **dados})
            except Exception:  # noqa: BLE001
                pass

    @property
    def modo(self) -> str:
        return (self.config.get("agente", "modo") or "equilibrado").lower()

    def modelo_principal(self) -> str:
        return self.config.get("motor", "modelo") or (self.perfil.modelo if self.perfil else "")

    def modelo_rapido(self) -> str:
        return (self.config.get("motor", "modelo_rapido")
                or (self.perfil.modelo_rapido if self.perfil else "")
                or self.modelo_principal())

    def escolher_modelo(self, texto: str, por_voz: bool, persona: dict | None = None) -> str:
        if persona and persona.get("modelo"):
            return persona["modelo"]
        livre_gb = psutil.virtual_memory().available / 1024**3
        if livre_gb < float(self.config.get("recursos", "ram_minima_gb", 1.5)):
            self._emitir("aviso", texto="Pouca RAM livre: usando o modelo rápido para não "
                                        "travar o PC.")
            return self.modelo_rapido()
        if por_voz and len(texto) < 120 and not re.search(
                r"(pesquis|crie|escrev|program|analis|organiz|planej|codigo|código)", texto, re.I):
            return self.modelo_rapido()
        return self.modelo_principal()

    def opcoes(self) -> dict[str, Any]:
        perfil = self.perfil
        threads = int(self.config.get("motor", "threads") or (perfil.threads if perfil else 0))
        uso = self.config.get("recursos", "uso", "equilibrado")
        nucleos = psutil.cpu_count(logical=False) or 2
        if uso == "economico":
            threads = max(1, min(threads or nucleos, nucleos // 2))
        elif uso == "maximo":
            threads = nucleos
        contexto = int(self.config.get("motor", "contexto") or (perfil.contexto if perfil else 0))
        if uso == "economico" and contexto:
            contexto = min(contexto, 4096)
        return {"contexto": contexto, "threads": threads,
                "temperatura": self.config.get("motor", "temperatura", 0.6),
                "manter_carregado": self.config.get("motor", "manter_carregado", "30m")}

    def prompt_sistema(self, persona: dict | None = None, consulta: str = "") -> str:
        nome = self.config.get("geral", "nome") or "Optimus"
        base = (persona or {}).get("prompt") or self.config.get("geral", "personalidade")
        partes = [base.replace("Optimus", nome)]
        agora = dt.datetime.now()
        partes.append(f"\n\nAgora: {agora.strftime('%d/%m/%Y %H:%M')}. Sistema: {sistema()}. "
                      f"Pasta de trabalho: {self.contexto.pasta_trabalho}.")
        usuario = self.config.get("geral", "usuario")
        if usuario:
            partes.append(f" O usuário se chama {usuario}.")
        if self.banco is not None:
            fatos = self.banco.buscar_fatos(consulta, limite=8)
            if fatos:
                partes.append("\n\nO que você sabe sobre o usuário:\n- " + "\n- ".join(fatos))
            try:
                trechos = self.banco.consultar(consulta, limite=3) if consulta else []
            except Exception:  # noqa: BLE001
                trechos = []
            if trechos:
                partes.append("\n\nTrechos da sua base de conhecimento que podem ajudar:\n" +
                              "\n---\n".join(f"[{t['titulo']}] {t['trecho'][:800]}"
                                               for t in trechos))
        if self.ferramentas:
            partes.append(_INSTRUCOES_FERRAMENTAS.replace(
                "{lista}", ", ".join(sorted(self.ferramentas))))
        if self.modo == "autonomo":
            partes.append(_INSTRUCOES_AUTONOMO)
        return "".join(partes)

    # Ferramentas
    def executar_chamada(self, chamada: ChamadaFerramenta) -> str:
        ferramenta = self.ferramentas.get(chamada.nome)
        if not ferramenta:
            return json.dumps({"erro": f"Ferramenta '{chamada.nome}' não existe ou está "
                                       "desligada nas configurações."}, ensure_ascii=False)
        avaliacao = ferramenta.avaliar(chamada.argumentos, self.contexto)
        nivel = NOMES_NIVEL.get(avaliacao.nivel, "?")
        self._emitir("ferramenta", nome=chamada.nome, argumentos=chamada.argumentos, nivel=nivel)
        if avaliacao.bloqueado:
            resultado = json.dumps({"erro": "Ação bloqueada pelo Optimus por segurança: "
                                            f"{avaliacao.motivo}. Se quiser mesmo, faça "
                                            "manualmente."}, ensure_ascii=False)
            self._auditar(chamada, avaliacao.nivel, "bloqueada", resultado)
            return resultado
        if precisa_confirmar(avaliacao.nivel, self.modo):
            self._emitir("confirmacao", nome=chamada.nome, argumentos=chamada.argumentos,
                         nivel=nivel, motivo=avaliacao.motivo)
            aprovado = bool(self.confirmar and self.confirmar(chamada, avaliacao))
            if not aprovado:
                self._auditar(chamada, avaliacao.nivel, "negada")
                self._emitir("negada", nome=chamada.nome)
                return json.dumps({"erro": "O usuário não autorizou esta ação. Não tente de "
                                           "novo; pergunte o que ele prefere."},
                                  ensure_ascii=False)
            decisao = "aprovada"
        else:
            decisao = "automatica"
        resultado = ferramenta.executar(chamada.argumentos, self.contexto)
        self._auditar(chamada, avaliacao.nivel, decisao, resultado)
        self._emitir("resultado", nome=chamada.nome, resultado=resultado[:2000])
        return resultado

    def _auditar(self, chamada, nivel, decisao, resultado=""):
        if self.auditoria:
            self.auditoria.registrar(chamada.nome, chamada.argumentos, nivel, decisao, resultado)

    # Conversa
    def _cortar_historico(self, historico: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limite_chars = max(4000, int(self.opcoes()["contexto"] or 8192) * 3)
        saida, total = [], 0
        for mensagem in reversed(historico):
            total += len(mensagem.get("content") or "")
            if total > limite_chars and saida:
                break
            saida.append(mensagem)
        return list(reversed(saida))

    def responder(self, texto: str, historico: list[dict[str, Any]] | None = None,
                  persona: dict | None = None, por_voz: bool = False) -> str:
        historico = list(historico or [])
        rapido = roteador_rapido(texto)
        if rapido and rapido[0] in self.ferramentas:
            chamada = ChamadaFerramenta(rapido[0], rapido[1])
            dados = json.loads(self.executar_chamada(chamada))
            if "erro" not in dados:
                resposta = (f"São {dados['hora']} de {dados['dia_semana']}, {dados['data']}."
                            if chamada.nome == "data_hora" else dados.get("mensagem", "Feito."))
                self._emitir("resposta", texto=resposta, modelo="roteador rápido")
                return resposta

        modelo = self.escolher_modelo(texto, por_voz, persona)
        mensagens = [{"role": "system", "content": self.prompt_sistema(persona, texto)}]
        mensagens += self._cortar_historico(historico)
        mensagens.append({"role": "user", "content": texto})
        esquemas = [f.esquema() for f in self.ferramentas.values()]
        nomes = set(self.ferramentas)
        max_passos = int(self.config.get("agente", "max_passos", 12))
        if self.modo == "autonomo":
            max_passos *= 2
        repetidas: dict[str, int] = {}

        for passo in range(max_passos):
            self._emitir("pensando", passo=passo + 1, modelo=modelo)
            try:
                resposta = self.motor.conversar(mensagens, modelo, esquemas, self.opcoes())
            except ErroMotor as erro:
                texto_erro = f"Não consegui falar com o motor de IA. {erro}"
                self._emitir("erro", texto=texto_erro)
                return texto_erro
            chamadas = resposta.chamadas
            conteudo = resposta.texto
            if not chamadas and conteudo:
                conteudo, chamadas = extrair_chamadas_do_texto(conteudo, nomes)
            if not chamadas:
                final = conteudo.strip() or "Pronto."
                self._emitir("resposta", texto=final, modelo=resposta.modelo or modelo,
                             velocidade=resposta.tokens_por_segundo)
                return final
            mensagens.append({
                "role": "assistant", "content": conteudo,
                "tool_calls": [{"id": c.id, "type": "function",
                                "function": {"name": c.nome, "arguments": c.argumentos}}
                               for c in chamadas],
            })
            for chamada in chamadas:
                assinatura = chamada.nome + json.dumps(chamada.argumentos, sort_keys=True)
                repetidas[assinatura] = repetidas.get(assinatura, 0) + 1
                if repetidas[assinatura] > 2:
                    resultado = json.dumps({"erro": "Você já chamou isto com os mesmos "
                                                    "argumentos. Responda com o que já tem."},
                                           ensure_ascii=False)
                else:
                    resultado = self.executar_chamada(chamada)
                mensagens.append({"role": "tool", "content": resultado,
                                  "tool_call_id": chamada.id, "name": chamada.nome})
        final = "Cheguei ao limite de passos para este pedido. Quer que eu continue?"
        self._emitir("resposta", texto=final, modelo=modelo)
        return final


def mensagens_para_historico(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converte as mensagens salvas no banco para o formato do motor."""
    return [{"role": l["papel"], "content": l["conteudo"]} for l in linhas
            if l["papel"] in ("user", "assistant")]
