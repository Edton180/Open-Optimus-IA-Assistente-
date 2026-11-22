# Mudanças

## 0.2 (em andamento)

Fase 1 do plano de novas funções:

- **Atualização pelo GitHub para qualquer instalação:** `optimus atualizar` (com `--verificar`,
  `--voltar`, `--canal beta`). Sem Git, baixa a release, confere o SHA-256, guarda a versão atual e
  permite voltar. Atualização automática opcional, com tempo de espera, janela de horário e versão
  maior sempre pedindo confirmação. Workflow que publica releases com `SHA256SUMS`.
- **Catálogo dinâmico de modelos** (`optimus modelos --atualizar`), com laboratório e licença de cada
  um e lançamentos recentes (Gemma 4, Qwen 3.6/3.8, GLM‑5.3, Nemotron 3, DeepSeek V4...). Qualquer
  modelo, mesmo sem avaliação, tem a memória estimada (`--cabe`) e pode ser testado no PC
  (`--avaliar`).
- **11 provedores novos** e **IA grátis automática** (`backend = "gratis"`: Groq, Gemini, Cerebras e
  OpenRouter em fila, trocando sozinho ao bater no limite).
- **Cofre de chaves** (`optimus chaves`): chaves de API no cofre criptografado do sistema.
- **Cliente MCP** (`[[mcp]]`, `optimus mcp`): outros apps e serviços viram ferramentas.

Fase 2 (produtividade):

- **Utilitários do dia a dia:** gerar senha forte, cara ou coroa, dado e sorteio, "quantos dias
  faltam pro Natal/Carnaval/Páscoa", cotação e conversão de moedas (dólar, euro, bitcoin...).
- **Textos rápidos:** guarde pix, endereço ou assinatura e diga "copia meu pix".
- **Caderno de notas** em Markdown: "anota que preciso comprar café", listar, ler, buscar, apagar.
- **Desfazer a organização de pasta** e **desligar/reiniciar daqui a X minutos** ("desliga o PC em
  30 minutos"; "cancela o desligamento").
- **Modo só executar:** o Optimus faz e fica quieto (confirmações de segurança continuam faladas).
- **Celular:** QR code para abrir o Optimus no telefone e **link de agenda (.ics)** que põe os
  lembretes no calendário do iPhone, Google Agenda ou Outlook.
- **MCP remoto:** envia o cabeçalho `MCP-Protocol-Version` depois do `initialize`.

- **Licença:** o Optimus passou para a PolyForm Noncommercial 1.0.0 — livre para uso não
  comercial e com licença comercial à parte com o proprietário (LICENSE-COMMERCIAL.md).
- **Travamentos:** um modelo que para de responder é interrompido com mensagem clara depois de
  `motor.tempo_sem_resposta` (120 s) sem nada, em vez de prender a tela por até 10 minutos; a tela
  não fica mais presa em "Pensando…" se o Optimus for reiniciado no meio da resposta.
- **Voz fora do ao vivo:** desligar o ao vivo (ou o 🔈) no meio da resposta corta a fala na hora.
- **Controle de verdade sem Home Assistant:** tomadas, interruptores e lâmpadas TP-Link Kasa pela
  Wi-Fi (procurar, ligar, desligar, alternar, brilho).
- **Webcams por cabo** (e a do notebook) como câmeras `usb:N`, ao vivo na tela Casa e em fotos.
- **Gestos pela câmera** no navegador (MediaPipe): parar, aprovar, negar, ao vivo e falar.
- **macOS:** instalador (Homebrew), volume, mídia, brilho, apps, energia, Bluetooth, rede local e
  início automático (launchd).

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

- **Hábitos e timers (recursos do painel):** acompanhamento de hábitos com sequência de dias
  seguidos (streak) — `habito_criar`, `habito_marcar`, `habitos_listar`, `habito_apagar` — e
  timers de contagem regressiva com nome — `timer_criar`, `timers_listar`, `timer_cancelar`.
  Tudo guardado no banco local (novas tabelas `habitos`, `habito_marcacoes`, `timers`). Os
  timers venceram no mesmo laço dos lembretes e tocam o alarme (interface/voz).
- **Histórico de copiados:** o Optimus guarda o que você copia (Ctrl+C) num histórico local,
  no seu PC, para você achar e reusar depois. Ferramentas `copiados_listar`, `copiado_usar`
  (coloca de volta na área de transferência), `copiado_apagar` e `copiados_limpar` (nova
  tabela `copiados`, preserva espaços/quebras, dedup e só os últimos N). A captura é **opt-in**
  e vem desligada (`[copiados] ativo = true` liga), porque ler a área de transferência é
  sensível. As ferramentas devolvem só uma prévia curta (o texto inteiro nunca vai para o
  modelo); `copiado_usar` restaura o item direto na área de transferência do PC. A aba
  Copiados no painel vem numa próxima fatia.
- **Rotinas (sequências que você dispara por um nome):** uma rotina é uma lista de passos em
  ordem — cada passo um pedido em texto, como você falaria com o Optimus (ex.: "bom dia" →
  resumo do dia, previsão do tempo, tocar playlist). Ferramentas `rotina_criar`,
  `rotinas_listar`, `rotina_executar` (devolve os passos em ordem para a interface/voz
  rodarem um a um) e `rotina_apagar` (novas tabelas `rotinas` e `rotina_passos`). Tudo no
  banco local. A aba Rotinas no painel vem numa próxima fatia.
- **Lembretes atrasados em destaque:** `listar_lembretes` agora marca os lembretes atrasados
  (pendentes cujo horário já passou) e os coloca no topo da lista; cada lembrete traz
  `atrasado` e `faltam_seg`, para a interface/voz destacarem o que está em atraso.
- **Palavra de ativação configurável:** dá para trocar a palavra que chama o Optimus na
  conversa por voz (padrão "optimus") — ex.: "me chame de Jarvis". Ferramentas
  `palavra_ativacao_definir` e `palavra_ativacao_ver` (guardam em `[voz] palavra_ativacao`).
- **Biblioteca de documentos (converse com os seus arquivos, offline):** `optimus biblioteca
  <pasta>` e as ferramentas `biblioteca_indexar`/`biblioteca_listar`/`biblioteca_esquecer`
  apontam o Optimus para uma pasta inteira (txt, md, csv, html, PDF...) e indexam tudo no
  conhecimento local (FTS5), sem mandar nada para fora. Idempotente: só reprocessa o que mudou e
  remove do índice o que sumiu. Depois, perguntas sobre os documentos são respondidas na hora, do
  próprio banco. Veja `optimus/biblioteca.py`.
- **Reconhece upgrade de peça e recomenda/baixa o modelo:** além da detecção de hardware e do
  aviso quando a máquina melhora (que já existiam), agora há ferramentas e o comando
  `optimus modelos` para ver o melhor modelo que cabe no PC por família, o que já está instalado
  e o que falta. Ferramentas `modelos_recomendados`, `modelo_baixar` (baixa pelo Ollama; vazio =
  o recomendado) e `modelo_usar`. Do PC fraco ao supercomputador, sempre o maior que couber.
- **Base de conhecimento própria embutida:** o Optimus já vem com conhecimento geral e benigno
  (sobre ele mesmo, primeiros socorros, conversões e medidas, redes e PC, referência de
  programação) em `optimus/knowledge/*.md`. Esses textos são indexados no banco local (FTS5) ao
  iniciar, então viram respostas prontas sem precisar da web nem gastar o modelo grande — ajuda a
  velocidade, principalmente em PC fraco. A indexação é idempotente (`optimus/conhecimento.py`):
  só reindexa o que mudou e remove fontes de arquivos que sumiram, sem duplicar.
- **Mais rápido e mais leve (velocidade e consumo):** a resposta agora tem um limite de
  tamanho (`num_predict`/`max_tokens`), então o modelo para de escrever em vez de se estender
  à toa — o que mais pesava em CPU fraca. Respostas faladas usam um limite curto
  (`motor.max_resposta_voz`, 320 tokens) e PCs em modo econômico limitam também o texto
  (`motor.max_resposta_economico`, 768). Em modo econômico, perguntas curtas vão direto para o
  modelo rápido. Vale para Ollama e para servidores compatíveis com a OpenAI.
- **Autoatualização pelo GitHub com barreira de privacidade (Zero-Leak):** `optimus/privacy_guard.py`
  varre tudo antes de qualquer commit automático, bloqueando arquivos sensíveis (`.db`, `.env`,
  `config.toml`, memórias, gravações) e mascarando chaves de API, tokens, chaves privadas, IPs, MACs,
  senhas de Wi-Fi e caminhos com o nome do usuário. `optimus/updater.py` baixa atualizações com `git pull`
  seguro (preservando os dados locais, que ficam fora do Git) e só commita/envia depois de uma revisão de
  privacidade limpa. Ferramentas `atualizacao_verificar`, `atualizacao_baixar` e `privacidade_revisar`.
  Veja [docs/atualizacao.md](docs/atualizacao.md).
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
