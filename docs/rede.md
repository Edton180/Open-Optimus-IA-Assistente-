# Outras IAs e outros computadores

O Optimus pode mandar os pedidos para mais de um lugar. Você cadastra **destinos** com prioridade; ele
usa o primeiro que estiver ligado e, se ele falhar no meio, passa para o próximo. "Este PC" entra sempre
com prioridade 5.

## Usar a placa de vídeo de outro PC da casa

No PC forte (o "servidor"), libere o Ollama na rede:

- **Windows:** Painel de Controle > Sistema > Variáveis de ambiente > nova variável de usuário
  `OLLAMA_HOST` = `0.0.0.0`, depois reinicie o Ollama.
- **Linux:** `sudo systemctl edit ollama` e adicione:

  ```
  [Service]
  Environment="OLLAMA_HOST=0.0.0.0"
  ```

  depois `sudo systemctl restart ollama`.

Baixe o modelo grande nele (`ollama pull qwen3.5:27b`). No notebook, em **Configurações > Outras IAs e
PCs > Adicionar destino**: tipo `ollama`, endereço `http://IP-DO-PC-FORTE:11434`, modelo `qwen3.5:27b`,
prioridade `1`. Pronto: quando o PC forte estiver ligado, o notebook usa ele; quando não, usa o próprio.

## Conectar outras IAs

Escolha o tipo, ponha a chave de API e (se quiser) o modelo. O endereço é preenchido sozinho.

| Tipo | Onde pegar a chave |
|---|---|
| `openai` | platform.openai.com |
| `anthropic` | console.anthropic.com |
| `gemini` | aistudio.google.com |
| `groq` | console.groq.com |
| `openrouter` | openrouter.ai (centenas de modelos com uma chave) |
| `deepseek` | platform.deepseek.com |
| `mistral` | console.mistral.ai |
| `lmstudio`, `llamacpp` | servidores locais, sem chave |

Ao usar um destino na nuvem, o texto da conversa (e os resultados das ferramentas) vai para esse
serviço. Para manter tudo privado, use só destinos locais.

## No config.toml

```toml
[[destinos]]
nome = "PC da sala"
backend = "ollama"
url = "http://192.168.0.20:11434"
modelo = "qwen3.5:27b"
prioridade = 1
ativo = true

[[destinos]]
nome = "OpenRouter"
backend = "openrouter"
chave_api = "sk-or-..."
modelo = "openrouter/auto"
prioridade = 9
ativo = true
```

Também dá para trocar o motor principal inteiro para a nuvem: `optimus config motor.backend groq` e
`optimus config motor.chave_api SUA_CHAVE`.
