# Sobre o Open Optimus

O Open Optimus é um assistente de IA pessoal que roda no seu próprio computador. Ele conversa
por texto e por voz, lembra do que importa, cuida de tarefas e lembretes, controla a casa
inteligente, escreve e edita código, pesquisa na web e usa modelos de IA locais (pelo Ollama)
ou de servidores compatíveis com a OpenAI. A ideia é ser um "cérebro" que funciona desde um PC
fraco até um supercomputador, sempre escolhendo o melhor modelo para o hardware disponível.

## Como falar com o Optimus

- **Por texto:** abra o aplicativo e escreva. As respostas aparecem na conversa.
- **Por voz:** diga a palavra de ativação (padrão "Optimus") ou dê duas palmas, e fale o pedido.
  Para interromper a fala do Optimus, diga "pare".
- **Ao vivo:** no modo HUD (núcleo), o Optimus fica ouvindo e respondendo em tempo real, com um
  orbe animado e anéis que mostram o uso de CPU, RAM e a velocidade em tokens por segundo.

## Modos de resposta

- **Pesquisar na web:** busca em DuckDuckGo, Bing, Wikipédia e Google Notícias antes de responder.
- **Gerar imagem:** cria imagens com Stable Diffusion local ou um gerador online gratuito.
- **Pensar a fundo:** liga o raciocínio passo a passo (mais lento, melhor para problemas difíceis).
- **Programar:** ativa o agente de código, que lê, edita, busca e roda testes nos seus projetos.
- O botão **Parar** cancela o pedido atual a qualquer momento.

## Velocidade e consumo

O Optimus é feito para ser rápido mesmo em máquinas modestas. Ele limita o tamanho das respostas
(para o modelo não escrever à toa), usa um modelo rápido para perguntas curtas em PCs fracos,
manda só as ferramentas que o pedido precisa e já faz pesquisas óbvias antes de chamar o modelo.
Em modo econômico, perguntas simples vão direto para o modelo rápido. Veja também
[[base_de_conhecimento]] para entender como ele responde sem precisar da internet.

## Privacidade

Seus dados (conversas, memórias, configurações, gravações) ficam no seu computador, fora do
controle de versão (Git). Quando o Optimus se autoatualiza pelo GitHub, uma barreira de
privacidade "Zero-Leak" varre tudo antes de qualquer envio, bloqueando arquivos sensíveis e
mascarando chaves, senhas, IPs e caminhos com o seu nome.

## Casa inteligente

Com o Home Assistant, o Optimus liga luzes, encadeia comandos (Assist), vê câmeras ao vivo,
conecta aparelhos Bluetooth e dá um relatório da casa com sugestões. Também fala com a Alexa.

## Perguntas comuns

- **O Optimus funciona sem internet?** Sim, se você usar um modelo local no Ollama. A pesquisa na
  web e alguns recursos online precisam de conexão, mas conversar, lembretes, tarefas e a base de
  conhecimento embutida funcionam offline.
- **Preciso de uma placa de vídeo cara?** Não. Ele roda em CPU, só mais devagar. Quando você
  troca uma peça (mais RAM, uma GPU nova), o Optimus percebe e sugere um modelo mais potente.
- **Em que sistemas roda?** Windows, Linux e macOS; no Android pelo Termux.
