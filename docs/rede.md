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

## Acessar o Optimus pelo celular de fora da casa (outra rede)

O `optimus gui --rede` libera o painel só na rede local (Wi-Fi da casa). Para acessar de qualquer
lugar (dados móveis, outro Wi-Fi), use um **túnel reverso**:

1. Defina uma senha forte (obrigatório):
   ```bash
   optimus config web.senha "sua-senha-forte-aqui"
   ```
2. Inicie com o modo túnel (já liga o `--rede` e mostra as instruções):
   ```bash
   optimus gui --tunel
   ```
3. Em outro terminal, rode um destes comandos (substitua a porta se mudou):
   ```bash
   # Cloudflare Tunnel (gratuito e recomendado)
   cloudflared tunnel --url http://127.0.0.1:8765

   # ou ngrok
   ngrok http 8765
   ```
4. Abra no celular a URL `https://...` que o túnel mostrar. A senha configurada será pedida.

**Segurança:** sem senha o painel fica aberto para quem tiver a URL. Nunca exponha a porta 8765
diretamente na internet (port-forward no roteador) sem autenticação e HTTPS. Cloudflare Tunnel e
ngrok já entregam HTTPS.

Instalação rápida do cloudflared:  
https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
