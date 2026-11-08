"""Catálogo de modelos locais de várias famílias e a escolha do melhor para o hardware.

Os tamanhos são o espaço aproximado do arquivo quantizado em 4 bits (o padrão do Ollama),
mais uma folga para o contexto. São estimativas: o que vale é se o modelo cabe na memória
útil (VRAM da placa, ou RAM quando não há placa).

Também guarda uma "assinatura" do hardware na configuração. Quando ela muda (mais RAM,
placa de vídeo nova), o Optimus avisa e oferece um modelo maior, sem trocar sozinho.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from optimus.hardware import Hardware, Perfil, memoria_util_gb


@dataclass(frozen=True)
class Modelo:
    nome: str          # nome no Ollama
    familia: str
    memoria_gb: float  # memória necessária (aproximada, 4 bits + contexto)
    tipo: str          # geral, raciocinio, codigo, visao
    descricao: str

    def para_dict(self) -> dict:
        return asdict(self)


CATALOGO: list[Modelo] = [
    # Qwen (Alibaba): o padrão do Optimus, ótimo em português e com ferramentas.
    Modelo("qwen3.5:0.8b", "Qwen", 1.2, "geral", "Mínimo, para PCs muito fracos"),
    Modelo("qwen3.5:2b", "Qwen", 2.2, "geral", "Leve e rápido, bom para voz"),
    Modelo("qwen3.5:4b", "Qwen", 3.6, "geral", "Equilíbrio para PC intermediário"),
    Modelo("qwen3.5:9b", "Qwen", 7.0, "geral", "Inteligente, pede 8 GB livres"),
    Modelo("qwen3.5:27b", "Qwen", 18.0, "geral", "Muito forte, placa de 24 GB"),
    Modelo("qwen3.5:35b-a3b", "Qwen", 24.0, "geral", "MoE: rápido na CPU com muita RAM"),
    Modelo("qwen2.5-coder:7b", "Qwen", 5.5, "codigo", "Especialista em programação"),
    Modelo("qwen2.5-coder:14b", "Qwen", 10.0, "codigo", "Programação, mais forte"),
    # Gemma (Google)
    Modelo("gemma3:1b", "Gemma (Google)", 1.2, "geral", "Pequeno do Google"),
    Modelo("gemma3:4b", "Gemma (Google)", 4.0, "visao", "Entende imagens"),
    Modelo("gemma3:12b", "Gemma (Google)", 9.5, "visao", "Forte, entende imagens"),
    Modelo("gemma3:27b", "Gemma (Google)", 19.0, "visao", "O maior Gemma"),
    # Llama (Meta)
    Modelo("llama3.2:1b", "Llama (Meta)", 1.5, "geral", "Pequeno da Meta"),
    Modelo("llama3.2:3b", "Llama (Meta)", 2.8, "geral", "Leve da Meta"),
    Modelo("llama3.1:8b", "Llama (Meta)", 6.0, "geral", "Clássico da Meta"),
    # DeepSeek (raciocínio; pensa antes de responder, por isso é mais lento)
    Modelo("deepseek-r1:1.5b", "DeepSeek", 1.6, "raciocinio", "Raciocínio, pequeno"),
    Modelo("deepseek-r1:7b", "DeepSeek", 5.5, "raciocinio", "Raciocínio"),
    Modelo("deepseek-r1:14b", "DeepSeek", 10.5, "raciocinio", "Raciocínio forte"),
    Modelo("deepseek-r1:32b", "DeepSeek", 21.0, "raciocinio", "Raciocínio muito forte"),
    # Phi (Microsoft)
    Modelo("phi4-mini", "Phi (Microsoft)", 3.2, "geral", "Pequeno da Microsoft"),
    Modelo("phi4:14b", "Phi (Microsoft)", 10.0, "raciocinio", "Bom em lógica e matemática"),
    # Mistral
    Modelo("mistral:7b", "Mistral", 5.0, "geral", "Clássico europeu"),
    Modelo("mistral-small3.2:24b", "Mistral", 16.0, "geral", "Forte, com visão"),
    # gpt-oss (OpenAI, pesos abertos)
    Modelo("gpt-oss:20b", "gpt-oss (OpenAI)", 14.0, "raciocinio", "Modelo aberto da OpenAI"),
    Modelo("gpt-oss:120b", "gpt-oss (OpenAI)", 66.0, "raciocinio", "Gigante, estação de trabalho"),
]


def familias() -> list[str]:
    vistos: list[str] = []
    for m in CATALOGO:
        if m.familia not in vistos:
            vistos.append(m.familia)
    return vistos


def cabem(memoria_gb: float, tipo: str | None = None) -> list[Modelo]:
    return [m for m in CATALOGO if m.memoria_gb <= memoria_gb and (tipo is None or m.tipo == tipo)]


def melhores_por_familia(hw: Hardware) -> list[dict]:
    """Para cada família, o maior modelo que cabe neste PC (e o próximo, que não cabe)."""
    memoria, _ = memoria_util_gb(hw)
    saida = []
    for familia in familias():
        da_familia = sorted((m for m in CATALOGO if m.familia == familia and m.tipo != "codigo"),
                            key=lambda m: m.memoria_gb)
        cabe = [m for m in da_familia if m.memoria_gb <= memoria]
        nao_cabe = [m for m in da_familia if m.memoria_gb > memoria]
        saida.append({"familia": familia,
                      "recomendado": cabe[-1].para_dict() if cabe else None,
                      "proximo": nao_cabe[0].para_dict() if nao_cabe else None})
    return saida


def tamanho(nome: str) -> float:
    """Memória aproximada de um modelo pelo nome (0 se não estiver no catálogo)."""
    for m in CATALOGO:
        if m.nome == nome:
            return m.memoria_gb
    return 0.0


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
