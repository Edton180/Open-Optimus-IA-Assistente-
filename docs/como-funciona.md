# Como o Optimus funciona

## O caminho de um pedido

1. **Roteador rápido.** Pedidos óbvios ("que horas são", "abre o YouTube") são resolvidos na hora, sem
   chamar o modelo. Em PC fraco isso é a diferença entre esperar 10 segundos e responder na hora.
2. **Escolha do modelo.** Se a RAM livre estiver baixa, ou for uma pergunta curta por voz, o Optimus usa
   o **modelo rápido**; senão, o principal. Cada persona pode fixar o próprio modelo.
3. **Prompt de sistema.** Junta a personalidade (sua ou da persona), data e hora, seu nome, os fatos que
   ele lembra sobre você e os trechos da base de conhecimento ligados à pergunta.
4. **Ciclo de ferramentas.** O modelo pede ferramentas; o Optimus avalia o risco, pergunta quando precisa,
   executa e devolve o resultado, até o modelo responder ou chegar ao limite de passos (12, ou 24 no
   modo autônomo). Chamadas repetidas são cortadas para não entrar em laço.
5. **Resposta.** Aparece na tela e, se você quiser, é falada frase por frase.

Modelos pequenos às vezes escrevem a chamada de ferramenta no texto em vez de usar a API. O Optimus
entende os formatos `<tool_call>{...}</tool_call>`, bloco ```json e JSON puro.

## Modos do agente

| Modo | Comportamento |
|---|---|
| Seguro | Pergunta antes de qualquer mudança (criar arquivo, abrir programa, comando desconhecido) |
| Equilibrado (padrão) | Faz sozinho o que dá para desfazer; pergunta antes do que é crítico |
| Autônomo | Recebe um objetivo, planeja e encadeia os passos até concluir. Ações críticas ainda perguntam |

```bash
optimus config agente.modo autonomo
optimus tarefa "baixe as 5 notícias mais lidas de hoje e salve um resumo em ~/Documentos/noticias.md"
```

## Ferramentas

| Grupo | Ferramentas |
|---|---|
| internet | `pesquisar_web`, `noticias`, `ler_pagina`, `clima` |
| arquivos | `listar_pasta`, `ler_arquivo`, `escrever_arquivo`, `copiar`, `mover`, `apagar`, `buscar_arquivos` |
| comandos | `executar_comando` (PowerShell no Windows, bash no Linux e Android) |
| programas | `abrir`, `info_sistema`, `listar_processos`, `encerrar_processo`, `energia` |
| teclado_mouse | `digitar`, `teclas`, `clicar`, `captura_tela`, `area_transferencia` (desligado por padrão) |
| lembretes | `criar_lembrete`, `listar_lembretes` |
| memoria | `lembrar`, `recordar`, `aprender`, `consultar_conhecimento` |
| casa | `casa_dispositivos`, `casa_controlar`, `camera_foto`, `bluetooth_procurar`, `rede_local` |
| geral | `data_hora`, `calcular` |

Cada grupo liga e desliga em **Configurações > Ferramentas** ou no `config.toml`, seção `[ferramentas]`.

## Memória

- **Fatos:** "lembre que meu aniversário é 10 de maio". Ficam para sempre e entram no prompt quando têm
  a ver com a conversa.
- **Base de conhecimento:** "aprenda este site: https://...", "estude o arquivo ~/manual.pdf". O texto é
  dividido em trechos e indexado (SQLite FTS5). Quando você pergunta algo relacionado, os trechos certos
  entram no prompt sozinhos, mesmo sem internet. Pelo terminal: `optimus aprender ARQUIVO_OU_LINK`.
- **Lembretes:** "me lembre de X em 20 minutos", "às 21:00", "de hora em hora". Aparecem na tela, como
  notificação do sistema e, com a voz ligada, falados.

Tudo fica no arquivo `optimus.db`, na pasta do Optimus, só no seu PC.

## Personas, projetos e conversa em grupo

- **Personas:** cada uma tem nome, prompt de sistema, modelo e voz. Vêm prontas: Optimus, Pesquisador,
  Programador e Livre (sem personalidade, só o modelo). Crie quantas quiser.
- **Projetos:** organize conversas em pastas (botão 📁 no histórico).
- **Conversa em grupo:** botão 👥. Várias personas respondem a mesma mensagem, uma depois da outra, cada
  uma vendo o que as anteriores disseram.
- **Biblioteca de prompts:** atalhos para pedidos frequentes (botão 📚).
