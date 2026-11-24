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

## Acessar o Optimus pelo celular fora da rede (4G/5G ou outro Wi-Fi)

O acesso remoto usa **Cloudflare Quick Tunnel**: o Optimus continua escutando apenas em
`127.0.0.1`, enquanto o processo `cloudflared` cria uma URL HTTPS temporária. Não é necessário
abrir portas no roteador nem colocar o computador diretamente na internet.

### Pela interface

1. Instale o `cloudflared` no computador:
   https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
2. Abra **Configurações > Celular e agenda** no Optimus.
3. Em **Acesso externo**, informe uma senha exclusiva com pelo menos 12 caracteres e toque em
   **Ativar acesso externo**.
4. Leia o QR code com o celular usando dados móveis (4G/5G) ou outro Wi-Fi. O segundo QR code
   assina a agenda no endereço externo.
5. Para encerrar, toque em **Encerrar acesso externo**. O túnel também é encerrado quando o
   servidor Optimus é desligado normalmente.

### Pelo terminal

Defina uma senha forte e inicie:

```bash
optimus config web.senha "uma-senha-exclusiva-com-mais-de-12-caracteres"
optimus gui --tunel
```

O comando requer o executável `cloudflared` instalado e cria o túnel enquanto o Optimus estiver
em execução. Use `Ctrl+C` para encerrar o servidor e o túnel.

### Limites e segurança

- O endereço Quick Tunnel é temporário e pode mudar ao reiniciar; gere um QR novo após reconectar.
- O computador precisa ficar ligado, sem suspensão, e conectado à internet.
- A senha protege o painel e as APIs. Use senha exclusiva, não a reutilize em outros serviços.
- A URL da agenda contém um token de acesso próprio: trate-a como privada e use **Trocar link da
  agenda** se ela for compartilhada por engano.
- Não configure encaminhamento de portas (port forwarding) no roteador para a porta do Optimus.
- O Cloudflare Tunnel é um serviço de terceiros e a conexão depende da disponibilidade da Cloudflare.
- Para um endereço permanente, configure um túnel nomeado na sua conta Cloudflare; o Quick Tunnel
  é destinado a testes e uso temporário.

## Descobrir dispositivos na rede local

- `rede_local` lê apenas o cache ARP/neighbor que o sistema já conhece; é rápido, mas pode omitir aparelhos.
- `rede_wifi_varrer` faz uma descoberta ativa limitada à LAN privada das interfaces IPv4 ativas, combinando ping e cache ARP/neighbor.
- Por segurança, a ferramenta só aceita uma sub-rede privada que pertença a uma interface local ativa e tenha no máximo 256 endereços por execução. Não varre IPs públicos, não faz port scan e não tenta autenticar ou alterar dispositivos.
- O resultado diferencia dispositivos que responderam ao ping dos que só estavam no cache. MAC pode não estar disponível e o fabricante/hostname ainda não são inferidos nesta versão; aparelhos que bloqueiam ping e não aparecem no cache podem não ser encontrados.

A varredura ativa pede confirmação pelo mecanismo de risco do Optimus. Faça isso apenas em redes que você administra ou tem autorização para diagnosticar.
