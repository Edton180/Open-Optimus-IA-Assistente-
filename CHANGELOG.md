# Mudanças

## 0.2 (em andamento)

Correções do primeiro uso real (i3 de 2 núcleos, `qwen3.5:2b`):

- **Respostas lentas (114 s, 318 s):** o modo "pensamento" do qwen3.5 estava ligado e o Optimus mandava
  ~40 ferramentas em todo pedido, estourando o contexto de 4.096 tokens. Agora: `think: false`, resposta
  em streaming, só as ferramentas da intenção do pedido (nenhuma numa conversa comum, no máximo 6 em
  modelos pequenos) e pesquisas óbvias feitas antes do modelo.
- **Lembretes criados sozinho:** consequência do contexto estourado (o modelo lia a própria instrução
  como pedido). Corrigido, com limpeza automática do lixo da 0.1 e lembretes duplicados ignorados.
- **Botões Aprovar/Negar:** cada confirmação tem um id, o servidor recusa respostas fora de hora e a tela
  mostra erro em vez de fingir que funcionou. Botões com cor sólida e texto legível.
- **Voz só falava parte da resposta:** a fala era cortada em 1.500 caracteres. Agora a resposta inteira é
  falada frase por frase, e o navegador fala com a voz dele se a do PC falhar.
- **Sem internet:** a pesquisa tenta DuckDuckGo, DuckDuckGo HTML, Bing e Wikipédia, nessa ordem; notícias
  pelo Google Notícias.

Novidades:

- Núcleo (HUD) com orbe animado, conversa **ao vivo** por voz (palavra "Optimus", duas palmas,
  interrupção com "pare"), abertura com o logo, relógio e anéis de CPU/RAM/tokens por segundo.
- Modos Pesquisar na web, Gerar imagem, Pensar a fundo e Programar; botão Parar que cancela o pedido.
- Gerar imagens (Stable Diffusion local ou gerador online gratuito), mostradas na conversa.
- Vozes Prime, Valkyrie, Nexus, Cyber, Stealth, Elite (ElevenLabs), Aurora, Lyra e Titan.
- Modelos de várias famílias com o melhor para o hardware e aviso quando o hardware melhora.
- Casa: comandos encadeados (Assist do Home Assistant), relatório com sugestões, Alexa, câmeras ao vivo,
  conectar Bluetooth.
- Agente de código (ler, editar, buscar, git, docker, testes) e especialistas Dev, DevOps, Pesquisa e
  Segurança; volume, brilho, mídia, desempenho, Wake-on-LAN e SSH para outros PCs.
- `optimus startup install|remove|status|restart|logs` (systemd, Agendador de Tarefas, Termux:Boot).

Ainda não validado em hardware real nesta versão: modelo real no Ollama (os testes usam um servidor que
fala o protocolo do Ollama), microfone físico, Whisper, Termux no Android e câmeras/Bluetooth reais.
