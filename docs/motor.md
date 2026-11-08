# Motor de IA

## Motores aceitos

| `motor.backend` | Para quê | Endereço padrão |
|---|---|---|
| `ollama` (padrão) | Modelos locais, Windows/Linux/macOS/Android, baixa modelos sozinho | `http://127.0.0.1:11434` |
| `llamacpp` | `llama-server` do llama.cpp | `http://127.0.0.1:8080/v1` |
| `lmstudio` | LM Studio | `http://127.0.0.1:1234/v1` |
| `openai` | Qualquer servidor compatível (vLLM, LocalAI, Jan) ou nuvem | o que você informar |
| `openai`, `anthropic`, `gemini`, `groq`, `openrouter`, `deepseek`, `mistral` | Provedores na nuvem, só pondo a chave | já preenchido |
| `demo` | Testar a interface sem IA | — |

## Escolha automática pelo hardware

`optimus hardware` mostra o que foi detectado:

```
Sistema: Windows 11 (AMD64)
CPU: AMD Ryzen 5 5600 (6 núcleos, 12 threads)
RAM: 32.0 GB (livre: 24.1 GB)
Placa de vídeo: NVIDIA GeForce RTX 3060 (12.0 GB)
Perfil: forte (PC forte ou placa de vídeo de 8 a 16 GB)
Modelo principal: qwen3.5:9b (alternativas: qwen3:8b, llama3.1:8b)
Modelo rápido (voz): qwen3.5:2b
Contexto: 16384 tokens, threads: 6, GPU: sim
Reconhecimento de voz: whisper small
```

Como decide:

- Com placa NVIDIA/AMD de 4 GB ou mais (detectada por `nvidia-smi`, `rocm-smi` ou pelo registro do
  Windows), usa 90% da VRAM como memória útil.
- Sem placa, usa a RAM menos uma reserva para o sistema (2 GB em PCs de até 8 GB, 4 GB acima) e nunca
  mais do que a RAM livre no momento. Assim o PC não trava.
- Sem placa mas com 22 GB ou mais de memória útil, escolhe o modelo **MoE** `qwen3.5:35b-a3b`: ele tem 35
  bilhões de parâmetros, mas só 3 bilhões trabalham por palavra, então responde rápido na CPU.
- Em PCs mínimo e leve, deixa um núcleo livre para o sistema.

`optimus instalar-modelo` baixa o modelo do perfil (e o modelo rápido); se ele não existir no seu Ollama,
tenta as alternativas.

## Usar outro modelo

Qualquer modelo do Ollama ou arquivo GGUF serve:

```bash
optimus instalar-modelo llama3.1:8b
optimus config motor.modelo llama3.1:8b
optimus config motor.modelo_rapido llama3.2:3b
```

Ou na interface: **Configurações > Motor de IA**, campo "Baixar modelo".

### Modelos sem filtro

O Optimus não adiciona filtros às conversas: o comportamento vem do modelo e do prompt que você escolher.
Se quiser um modelo com menos recusas, a comunidade publica versões ajustadas de modelos abertos no
Ollama e no Hugging Face (procure por "abliterated" ou "uncensored"). Instale como qualquer outro modelo
e escreva a personalidade que quiser em **Configurações > Geral** ou numa persona. Lembre do
[aviso de responsabilidade](../README.md).

## Desempenho

| Opção | Efeito |
|---|---|
| `recursos.uso = "economico"` | Metade dos núcleos e contexto de até 4.096 tokens. Bom para jogar ou PC fraco |
| `recursos.uso = "equilibrado"` | Padrão: deixa folga para o sistema |
| `recursos.uso = "maximo"` | Todos os núcleos |
| `recursos.ram_minima_gb` | Abaixo dessa RAM livre, usa o modelo rápido (padrão 1,5 GB) |
| `recursos.prioridade_baixa` | O processo do Optimus roda com prioridade baixa |
| `motor.manter_carregado` | Quanto tempo o modelo fica na memória depois de usado (padrão `30m`) |
| `motor.contexto` / `motor.threads` | 0 = automático pelo perfil |

Dica para placas NVIDIA no Windows: atualize o driver; o Ollama usa a placa sozinho.
