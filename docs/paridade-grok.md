# Auditoria de paridade funcional com Grok

Esta auditoria compara capacidades públicas documentadas do Grok com o que existe no
Open Optimus. "Implementado" significa que há código no repositório; não significa que
qualquer modelo, provedor ou hardware ofereça a mesma qualidade ou disponibilidade.

## Estado da auditoria

| Capacidade | Estado no Optimus | Observação |
|---|---|---|
| Conversa e raciocínio | Implementado, dependente do modelo | O Optimus usa o modelo local ou provedor configurado. A qualidade de raciocínio não é idêntica entre modelos. |
| Pesquisa web em tempo real | Implementado; correção nesta atualização | Combina buscadores, pontua relevância, remove duplicatas, filtra resultados sem relação, resolve redirecionamentos Bing e limita espera. |
| Leitura e síntese de fontes | Implementado | A ferramenta ler_pagina abre páginas; o agente recebe instruções para priorizar fontes primárias, conferir datas e limitar a leitura a três páginas. |
| Pesquisa pública no X | Implementado com requisito externo | pesquisar_x usa a API oficial do X. Exige Bearer Token com acesso à busca recente; não faz scraping nem inventa posts se não houver credencial. |
| Deep Search / pesquisa longa | Parcial | Existe especialista de pesquisa (delegar), que pode pesquisar e ler páginas. Ainda não existe uma execução multi-etapas com painel de fontes, trilha de evidências e síntese de conflitos equivalente ao DeepSearch. |
| Agentes paralelos | Não implementado | delegar cria um especialista por chamada, em execução sequencial. O modo multiagente paralelo do Grok não deve ser anunciado como disponível. |
| Voz | Implementado | Reconhecimento e síntese de voz, conversa ao vivo no navegador e estúdio de voz; latência depende do PC, modelo e motor de voz. |
| Geração de imagens | Implementado | Usa gerador local ou serviço online configurado. Disponibilidade e qualidade dependem do serviço. |
| Geração de vídeos a partir de texto | Não implementado | O estúdio possui transcrição, legendas, dublagem e edição de áudio/vídeo, mas isso não equivale a text-to-video. |
| Análise de arquivos e PDF | Implementado | Há leitura de arquivos e ferramentas de PDF; formatos e limites dependem dos módulos instalados. |
| Compreensão de imagens | Parcial / dependente do motor | O formato de mensagens aceita imagens em alguns caminhos; é necessário usar um modelo multimodal compatível. Não é garantido em todos os modelos locais. |
| Memória entre conversas | Implementado; correção nesta atualização | SQLite guarda mensagens e fatos. O roteador agora seleciona buscar_conversas para perguntas sobre resultados, decisões e conversas anteriores. |
| Instruções personalizadas e personas | Implementado | Personalidade configurável e personas com prompts próprios. |
| Código e assistência de programação | Implementado | Ferramentas para ler, editar, testar e versionar projetos. |
| Editor tipo Canvas | Não implementado como recurso dedicado | É possível criar/editar arquivos, mas não há editor colaborativo inline equivalente. |
| Compartilhamento público de conversas | Não implementado | O histórico é local; não há link público nativo de compartilhamento. |

## Correções desta atualização

- Busca web consulta vários motores em vez de aceitar cegamente a primeira lista.
- Resultados são pontuados por termos no título e no trecho, com expansão controlada para BRB / Banco de Brasília / BSLI3 / BSLI4.
- Resultados sem relação são descartados; quando nenhum resultado passa o filtro, a ferramenta retorna erro explícito em vez de conteúdo enganoso.
- DuckDuckGo e Bing recebem timeouts menores; links de tracking do Bing são convertidos para o destino real.
- A pesquisa no X usa a API oficial e um token opcional guardado no cofre de credenciais.
- O agente recebe instruções para não abrir mais de três páginas, verificar entidade/data e não inventar cotações ou publicações.
- Perguntas sobre conversas anteriores acionam a busca no histórico local.

## Configurar a pesquisa no X

1. Crie um projeto no portal de desenvolvedores do X e obtenha um Bearer Token com permissão de leitura para a busca recente.
2. No terminal do Optimus, grave o segredo no cofre:

   optimus chaves definir provedores.x_api_chave

3. Reinicie o Optimus. Pergunte, por exemplo: "pesquise no X publicações recentes sobre Banco de Brasília".

Sem token ou sem permissão de API, a pesquisa web normal continua funcionando; a ferramenta do X informa claramente que não está disponível.

## Limites e segurança

- A pesquisa web não transforma snippets em fatos: fontes devem ser abertas e comparadas antes de afirmações importantes.
- Posts do X são declarações de usuários, não confirmação independente de acontecimentos.
- A busca recente da API do X depende do acesso e dos limites do plano da conta.
- Não se implementam recursos furtivos de espionagem, keylogging clandestino, agentes ocultos ou controle de dispositivos sem consentimento. Administração remota deve ser visível, autorizada e auditável.
- Geração de vídeo, multiagentes paralelos, Canvas e compartilhamento público continuam como lacunas; não devem ser apresentados como concluídos.
