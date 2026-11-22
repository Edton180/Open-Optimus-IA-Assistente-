"""Catálogo de modelos locais de várias famílias e a escolha do melhor para o hardware.

Os tamanhos são o espaço aproximado do arquivo quantizado em 4 bits (o padrão do Ollama),
mais uma folga para o contexto. São estimativas: o que vale é se o modelo cabe na memória
útil (VRAM da placa, ou RAM quando não há placa).

O catálogo **não é fixo no código**: fica em `optimus/catalogo/modelos.json` e pode ser
atualizado pelo GitHub (`optimus modelos --atualizar`) sem precisar de versão nova do
Optimus. A cópia baixada fica em `OPTIMUS_HOME/modelos.json` e só vale se for mais nova.

Modelos **fora do catálogo** (lançamentos recentes, ainda sem avaliação) também funcionam:
`estimar()` calcula a memória pelo tamanho e pela quantização (do nome ou do próprio Ollama)
e `avaliar()` roda um teste rápido de velocidade e de português no seu PC.

Também guarda uma "assinatura" do hardware na configuração. Quando ela muda (mais RAM,
placa de vídeo nova), o Optimus avisa e oferece um modelo maior, sem trocar sozinho.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from optimus.hardware import Hardware, Perfil, memoria_util_gb

log = logging.getLogger(__name__)

ARQUIVO_EMBUTIDO = Path(__file__).with_name("catalogo") / "modelos.json"
URL_CATALOGO = "https://raw.githubusercontent.com/{repo}/main/optimus/catalogo/modelos.json"


@dataclass(frozen=True)
class Modelo:
    nome: str          # nome no Ollama
    familia: str
    memoria_gb: float  # memória necessária (aproximada, 4 bits + contexto)
    tipo: str          # geral, raciocinio, codigo, visao
    descricao: str
    laboratorio: str = ""
    licenca: str = ""
    confirmado: bool = True  # False = nome no Ollama ainda não conferido (só em "novidades")
    capacidades: tuple[str, ...] = field(default=())

    def para_dict(self) -> dict:
        d = asdict(self)
        d["capacidades"] = list(self.capacidades)
        return d


def _ler(caminho: Path) -> dict | None:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if isinstance(dados.get("modelos"), list) and dados["modelos"]:
            return dados
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _arquivo_usuario() -> Path:
    from optimus.config import pasta_base

    return pasta_base() / "modelos.json"


def _converter(dados: dict) -> list[Modelo]:
    saida = []
    campos = set(Modelo.__dataclass_fields__)
    for item in dados["modelos"]:
        try:
            limpo = {k: v for k, v in item.items() if k in campos}
            limpo["capacidades"] = tuple(limpo.get("capacidades") or ())
            limpo["memoria_gb"] = float(limpo["memoria_gb"])
            saida.append(Modelo(**limpo))
        except (KeyError, TypeError, ValueError):
            continue  # um item estragado não derruba o catálogo
    return saida


def carregar_catalogo() -> list[Modelo]:
    """Usa o catálogo baixado do GitHub se ele for mais novo que o embutido."""
    embutido = _ler(ARQUIVO_EMBUTIDO) or {"versao": 0, "modelos": []}
    melhor = embutido
    try:
        baixado = _ler(_arquivo_usuario())
    except Exception:  # noqa: BLE001 - pasta do usuário indisponível
        baixado = None
    if baixado and int(baixado.get("versao", 0)) > int(embutido.get("versao", 0)):
        melhor = baixado
    return _converter(melhor) or _converter(embutido)


CATALOGO: list[Modelo] = carregar_catalogo()


def recarregar() -> list[Modelo]:
    CATALOGO[:] = carregar_catalogo()
    return CATALOGO


def atualizar_catalogo(repo: str = "", baixar=None) -> dict:
    """Baixa o catálogo mais novo do GitHub. Só grava se for válido e mais novo."""
    from optimus.releases import REPO_PADRAO

    url = URL_CATALOGO.format(repo=repo or REPO_PADRAO)
    try:
        if baixar is None:
            import httpx

            r = httpx.get(url, timeout=20, follow_redirects=True)
            r.raise_for_status()
            conteudo = r.text
        else:
            conteudo = baixar(url)
        dados = json.loads(conteudo)
    except Exception as erro:  # noqa: BLE001
        return {"ok": False, "erro": f"Não consegui baixar o catálogo: {erro}"}
    if not isinstance(dados.get("modelos"), list) or not _converter(dados):
        return {"ok": False, "erro": "O catálogo baixado não é válido; mantive o atual."}
    atual = max((int((_ler(c) or {}).get("versao", 0)) for c in
                 (ARQUIVO_EMBUTIDO, _arquivo_usuario())), default=0)
    if int(dados.get("versao", 0)) <= atual:
        return {"ok": True, "mudou": False, "mensagem": "O catálogo de modelos já está em dia."}
    destino = _arquivo_usuario()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    recarregar()
    return {"ok": True, "mudou": True, "modelos": len(CATALOGO),
            "mensagem": f"Catálogo atualizado: {len(CATALOGO)} modelos."}


def familias() -> list[str]:
    vistos: list[str] = []
    for m in CATALOGO:
        if m.confirmado and m.familia not in vistos:
            vistos.append(m.familia)
    return vistos


def cabem(memoria_gb: float, tipo: str | None = None) -> list[Modelo]:
    return [m for m in CATALOGO if m.confirmado and m.memoria_gb <= memoria_gb
            and (tipo is None or m.tipo == tipo)]


def melhores_por_familia(hw: Hardware) -> list[dict]:
    """Para cada família, o maior modelo que cabe neste PC (e o próximo, que não cabe)."""
    memoria, _ = memoria_util_gb(hw)
    saida = []
    for familia in familias():
        da_familia = sorted((m for m in CATALOGO if m.familia == familia and m.tipo != "codigo"
                             and m.confirmado),
                            key=lambda m: m.memoria_gb)
        cabe = [m for m in da_familia if m.memoria_gb <= memoria]
        nao_cabe = [m for m in da_familia if m.memoria_gb > memoria]
        saida.append({"familia": familia,
                      "recomendado": cabe[-1].para_dict() if cabe else None,
                      "proximo": nao_cabe[0].para_dict() if nao_cabe else None})
    return saida


def tamanho(nome: str) -> float:
    """Memória aproximada de um modelo pelo nome (catálogo; senão, estimada pelo nome)."""
    for m in CATALOGO:
        if m.nome == nome:
            return m.memoria_gb
    return estimar(nome).get("memoria_gb", 0.0)


def novidades() -> list[dict]:
    """Modelos recentes já no catálogo mas ainda não conferidos (não são recomendados)."""
    return [m.para_dict() for m in CATALOGO if not m.confirmado]


# ---------------------------------------------------------------------- modelos sem avaliação
_BYTES_POR_PARAMETRO = {  # aproximado, incluindo a sobra de cada formato
    "q2": 0.35, "q3": 0.45, "q4": 0.58, "q5": 0.7, "q6": 0.82, "q8": 1.07,
    "fp16": 2.0, "f16": 2.0, "bf16": 2.0, "fp32": 4.0, "f32": 4.0, "nvfp4": 0.55, "mxfp4": 0.55,
}
_PARAMS = re.compile(r"(?<![a-z0-9])(?:e)?(\d+(?:\.\d+)?)\s*([bmt])(?![a-z])", re.IGNORECASE)
_ATIVOS = re.compile(r"[-_:]a(\d+(?:\.\d+)?)b", re.IGNORECASE)
_QUANT = re.compile(r"(nvfp4|mxfp4|bf16|fp16|f16|fp32|f32|q[2-8])", re.IGNORECASE)


def _bilhoes(valor: str, unidade: str) -> float:
    n = float(valor)
    return {"m": n / 1000, "b": n, "t": n * 1000}[unidade.lower()]


def estimar(nome: str, info: dict | None = None) -> dict:
    """Estima a memória de qualquer modelo, mesmo fora do catálogo e sem benchmark.

    Usa, nesta ordem: os dados do Ollama (`info`, de `/api/show`: total de parâmetros,
    quantização e capacidades) e o próprio nome ("qwen9:14b-a3b-q8_0" → 14 bilhões, MoE com
    3 ativos, 8 bits). Sem dado de quantização, supõe 4 bits, o padrão do Ollama.
    """
    info = info or {}
    detalhes = info.get("details") or {}
    params = 0.0
    for chave, valor in (info.get("model_info") or {}).items():
        if chave.endswith("parameter_count") and isinstance(valor, (int, float)):
            params = float(valor) / 1e9
            break
    if not params and detalhes.get("parameter_size"):
        m = _PARAMS.search(str(detalhes["parameter_size"]))
        if m:
            params = _bilhoes(*m.groups())
    alvo = nome.split("/")[-1]
    if not params:
        tag = alvo.split(":", 1)[1] if ":" in alvo else alvo
        sem_ativos = _ATIVOS.sub("", tag)
        m = _PARAMS.search(sem_ativos) or _PARAMS.search(_ATIVOS.sub("", alvo))
        if m:
            params = _bilhoes(*m.groups())
    quant_txt = str(detalhes.get("quantization_level") or "")
    q = _QUANT.search(quant_txt) or _QUANT.search(alvo)
    quant = q.group(1).lower() if q else "q4"
    if not params:
        return {"nome": nome, "conhecido": False, "memoria_gb": 0.0, "quantizacao": quant,
                "capacidades": list(info.get("capabilities") or [])}
    ativos = _ATIVOS.search(alvo)
    contexto = 0.6 + min(params, 70) * 0.025  # folga do contexto/cache, cresce devagar
    memoria = round(params * _BYTES_POR_PARAMETRO.get(quant, 0.58) + contexto, 1)
    return {"nome": nome, "conhecido": True, "parametros_b": round(params, 2),
            "ativos_b": float(ativos.group(1)) if ativos else None, "quantizacao": quant,
            "memoria_gb": memoria, "capacidades": list(info.get("capabilities") or [])}


def cabe_neste_pc(nome: str, hw: Hardware, info: dict | None = None) -> dict:
    """Diz se um modelo qualquer cabe na memória útil deste PC."""
    estimativa = dict(next((m.para_dict() for m in CATALOGO if m.nome == nome), None)
                      or estimar(nome, info))
    memoria, usou_ram = memoria_util_gb(hw)
    precisa = estimativa.get("memoria_gb", 0.0)
    estimativa.update({"memoria_util_gb": round(memoria, 1), "usando_ram": usou_ram,
                       "cabe": bool(precisa) and precisa <= memoria})
    if not precisa:
        estimativa["aviso"] = "Não deu para estimar o tamanho; teste com cuidado."
    return estimativa


PERGUNTA_TESTE = ("Responda em português, em uma frase curta: qual é a capital do Brasil e "
                  "quanto é 12 vezes 7?")


def avaliar(motor, nome: str) -> dict:
    """Teste rápido de um modelo neste PC: velocidade, português e uma conta simples.

    Serve para modelos novos que ainda não têm avaliação pública. O resultado fica em
    `OPTIMUS_HOME/avaliacoes.json`.
    """
    inicio = time.perf_counter()
    try:
        resposta = motor.conversar([{"role": "user", "content": PERGUNTA_TESTE}], nome,
                                   opcoes={"max_resposta": 80, "temperatura": 0})
    except Exception as erro:  # noqa: BLE001
        return {"modelo": nome, "ok": False, "erro": f"O modelo não respondeu: {erro}"}
    segundos = time.perf_counter() - inicio
    texto = (resposta.texto or "").lower()
    acertos = {"capital": "brasília" in texto or "brasilia" in texto, "conta": "84" in texto,
               "portugues": bool(re.search(r"\b(é|capital|vezes|resultado|são)\b", texto))}
    nota = round(10 * sum(acertos.values()) / len(acertos), 1)
    resultado = {"modelo": nome, "ok": True, "segundos": round(segundos, 2),
                 "tokens_por_segundo": round(resposta.tokens_por_segundo or 0.0, 1),
                 "acertos": acertos, "nota": nota, "resposta": resposta.texto[:300]}
    try:
        from optimus.config import pasta_base

        arq = pasta_base() / "avaliacoes.json"
        todas = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
        todas[nome] = resultado | {"quando": time.strftime("%Y-%m-%d %H:%M")}
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(todas, ensure_ascii=False, indent=1), encoding="utf-8")
    except (OSError, ValueError):
        pass
    return resultado


def assinatura(hw: Hardware) -> str:
    placa = f"{hw.placa.nome}:{hw.placa.vram_gb}x{hw.placa.quantidade}" if hw.placa else "sem-placa"
    return f"ram{round(hw.ram_total_gb)}|{placa}|cpu{hw.nucleos_logicos}"


def verificar_upgrade(config, hw: Hardware, perfil: Perfil) -> dict | None:
    """Compara com o hardware da última vez. Devolve um aviso se dá para usar um modelo maior.

    Na primeira execução só guarda a assinatura. O usuário decide se troca (botão no painel).
    """
    atual = assinatura(hw)
    anterior = config.get("motor", "hardware_assinatura", "")
    if not anterior:
        config.definir("motor", "hardware_assinatura", atual)
        if getattr(config, "caminho", None):  # sem arquivo (testes): não grava nada
            try:
                config.salvar()
            except OSError:
                pass
        return None
    escolhido = config.get("motor", "modelo", "")
    if anterior == atual:
        return None
    if not escolhido:
        # Modo automático: o perfil novo já vale. Só informa.
        return {"texto": f"Seu hardware mudou. Agora o modelo recomendado é {perfil.modelo}.",
                "modelo": perfil.modelo, "automatico": True}
    if tamanho(perfil.modelo) > tamanho(escolhido) > 0:
        return {"texto": (f"Seu hardware mudou e agora cabe um modelo maior: {perfil.modelo} "
                          f"(você usa {escolhido}). Quer trocar?"), "modelo": perfil.modelo}
    return None


def aceitar_upgrade(config, hw: Hardware, modelo: str) -> None:
    config.definir("motor", "modelo", modelo)
    config.definir("motor", "hardware_assinatura", assinatura(hw))
    config.salvar()


def dispensar_aviso(config, hw: Hardware) -> None:
    config.definir("motor", "hardware_assinatura", assinatura(hw))
    config.salvar()
