# Auditoria de capacidades do Grok no Open Optimus

Este documento registra uma comparação funcional para orientar o desenvolvimento do Optimus.
Não representa integração com Grok, xAI ou X. O Optimus usa o motor local ou o provedor que
o usuário configurar.

## Estado por capacidade

| Capacidade | Estado no Optimus | O que falta / observação |
|---|---|---|
| Conversa e raciocínio | Implementado, dependente do modelo | Qualidade e contexto dependem do LLM escolhido e do hardware. |
| Pesquisa web em tempo real | Implementada | Combina buscadores, pontua relevância, deduplica, filtra e resolve redirecionamentos; ainda requer testes reais de qualidade em consultas variadas. |
| Leitura e síntese de fontes | Implementada | `ler_pagina` abre páginas; a síntese depende do motor e da disponibilidade do site. |
| Deep Search multi-etapas | Parcial | Existe delegação para especialistas, mas falta orquestração de pesquisa em etapas, trilha de evidências, comparação sistemática de fontes e síntese de divergências. |
| Agentes paralelos | Não implementado | A delegação atual é sequencial; não anunciar execução paralela como disponível. |
| Voz | Implementada | STT/TTS e conversa ao vivo; latência e qualidade dependem dos motores e dispositivos. |
| Geração de imagens | Implementada | Depende do gerador local ou serviço configurado. |
| Geração de vídeo a partir de texto | Não implementada | O estúdio faz transcrição, legendas, dublagem e edição; isso não é text-to-video. |
| Análise de arquivos e PDFs | Implementada | Formatos e limites dependem dos módulos opcionais instalados. |
| Compreensão de imagens | Parcial | Depende de um motor multimodal; não é garantida em todos os modelos locais. |
| Memória entre conversas | Implementada | SQLite guarda histórico e fatos; a recuperação depende do roteamento e da consulta. |
| Personas e instruções personalizadas | Implementadas | Personas configuráveis com prompt, modelo e voz. |
| Código e automação de projetos | Implementados parcialmente | Há ferramentas de arquivos, terminal, Git e testes; precisa de E2E por plataforma e projetos reais. |
| Editor colaborativo tipo Canvas | Não implementado | A edição de arquivos não equivale a um editor colaborativo inline. |
| Compartilhamento público de conversas | Não implementado | Histórico local, sem links públicos nativos. |

## Escopo e não objetivos

- Não adicionar integração com Grok/xAI nem com X/Twitter.
- Não tratar presença de um módulo, botão ou documentação como prova de funcionamento.
- Cada capacidade deve ser validada com testes unitários, integração e E2E no sistema operacional correspondente.
- Recursos que dependem de credenciais, hardware ou serviços externos devem mostrar claramente o pré-requisito e falhar de forma explícita.

## Prioridades técnicas

1. Corrigir e validar a pesquisa web com consultas reais e conjuntos de relevância, incluindo finanças, notícias, documentação e consultas ambíguas.
2. Fazer o agente consultar o histórico local quando a pergunta se referir a decisões e resultados anteriores.
3. Implementar Deep Search com plano de pesquisa, fontes rastreáveis, leitura, citações, confronto de evidências e síntese final.
4. Implementar execução paralela de especialistas com limites de concorrência, cancelamento e isolamento de falhas.
5. Criar testes E2E para cada tela, botão, fluxo de ferramenta e modo de execução.
6. Manter as lacunas explícitas até a implementação e validação correspondentes.
