# Matriz de capacidades: Optimus x Project NOMAD

Este documento usa o [Project NOMAD](https://github.com/Crosstalk-Solutions/project-nomad) como referência funcional pública. O objetivo é oferecer as capacidades equivalentes no Optimus e ampliar a experiência com agente autônomo, voz em português brasileiro, integração com o computador e casa inteligente.

**Importante:** "paridade" significa cobrir os casos de uso com implementação própria ou integração documentada. Não significa copiar marca, identidade visual, conteúdo de terceiros ou código sem cumprir a licença. O repositório NOMAD declara Apache License 2.0; reutilização de código deve manter avisos, licença e NOTICE aplicáveis. Os conteúdos baixados têm licenças próprias e precisam ser verificados individualmente.

## Matriz inicial

| Área de referência | NOMAD apresenta | Situação encontrada no Optimus | Evolução necessária |
|---|---|---|---|
| Command Center | Painel web/API que gerencia serviços | Painel web local próprio já existe | Painel de módulos, serviços, health, logs, filas e permissões |
| IA local/remota | Ollama e APIs compatíveis | Já existe Ollama, modelos remotos, catálogo de modelos, avaliação de hardware e ferramentas de download | Melhorar benchmark reprodutível, comparação histórica e políticas de atualização/armazenamento; não duplicar catálogo nem download existentes |
| RAG/Knowledge Base | Upload, busca semântica e Qdrant | Já existe SQLite FTS5, aprendizagem de sites/arquivos e contexto automático | Ingestão incremental multimodal, embeddings locais, citações de página/trecho, filtros e reindexação |
| Biblioteca offline | Kiwix e arquivos ZIM | Não identificada na auditoria inicial | Catálogo ZIM, downloads retomáveis, checksum, idioma, licença e leitor |
| Educação | Kolibri, cursos e progresso | Não identificada na auditoria inicial | Integração opcional, perfis, progresso e conteúdo offline |
| Mapas offline | ProtoMaps/PMTiles | Não identificada na auditoria inicial | PMTiles, download regional, pesquisa e atribuição de dados |
| Ferramentas de dados | CyberChef | Há ferramentas e utilitários do agente, mas não foi confirmada suíte equivalente | Laboratório de dados com receitas, encoding, hash, compressão e análise |
| Notas | FlatNotes/Markdown | Não confirmada uma aplicação de notas completa | Notas Markdown, tags, anexos, pesquisa, backlinks e exportação |
| Catálogo de apps | Supply Depot e containers | Plugins de ferramentas existem; catálogo de apps não foi confirmado | Catálogo assinado, permissões, versões e instalação consentida |
| Benchmark | Pontuação de hardware/leaderboard | Detecção de hardware e perfis de modelo já existem | Benchmark reprodutível, relatórios locais e publicação opt-in |
| Atualizações | Atualizações opt-in de core/apps/conteúdo | Já existem atualização do core, backup em instalações de release, rollback para instalações Git/release e canais stable/beta | Evoluir migrações de dados versionadas, atualização independente de módulos/conteúdos e recuperação testada após falha |
| Setup wizard | Configuração inicial e coleções | Instaladores Windows/Linux/Android já existem | Wizard modular, idioma, caminhos, espaço e perfil de hardware |
| Offline-first | Acesso offline a conteúdo e serviços | Agente e modelos locais já existem; pesquisa web depende de rede | Matriz offline explícita e teste sem conectividade |
| Idiomas | Interface/conteúdo majoritariamente inglês conforme README/FAQ | Optimus prioriza português brasileiro | pt-BR como idioma principal e seleção por módulo |

## Princípios arquiteturais

1. **Base leve, módulos opcionais:** o núcleo do Optimus não deve exigir Qdrant, Docker, GPU ou grandes downloads para iniciar.
2. **Dados locais primeiro:** SQLite para metadados e funcionalidades básicas; índices vetoriais e serviços externos como backends opcionais.
3. **Integração upstream:** Kiwix, Kolibri, PMTiles/Protomaps, Qdrant e ferramentas equivalentes devem ser integrados por adaptadores, evitando forks desnecessários.
4. **Agente como camada unificadora:** o agente consulta módulos por ferramentas com permissões, confirmações e fontes rastreáveis.
5. **Citações e proveniência:** respostas baseadas em documentos indicam arquivo, página/seção e trecho; conteúdo web indica URL e data de captura.
6. **Segurança por padrão:** serviços escutam em localhost; acesso remoto exige autenticação e configuração explícita. Instalação de apps e containers sempre exige consentimento.
7. **Preservação de dados:** migrações fazem backup, são reversíveis quando possível e nunca apagam memória, credenciais, conversas ou documentos automaticamente.
8. **Sem simulação:** indisponível, não instalado, sem licença, sem hardware ou sem conexão devem aparecer como estados reais.

## Fases de implementação

- [ ] Inventariar arquitetura atual, dados, atualizador, UI e cobertura de testes (incluindo recursos já existentes para evitar duplicação).
- [ ] Consolidar Knowledge Center com ingestão, proveniência e citações.
- [ ] Criar catálogo modular e painel de serviços.
- [ ] Integrar biblioteca offline Kiwix/ZIM.
- [ ] Implementar notas e Data Lab.
- [ ] Integrar Kolibri e mapas PMTiles.
- [ ] Ampliar benchmark local reprodutível e publicação opt-in, preservando catálogo, avaliação de hardware e downloads de modelos já existentes.
- [ ] Evoluir wizard e migrações de dados; preservar backup, rollback e canais stable/beta já existentes; adicionar atualização independente de módulos/conteúdos.
- [ ] Integrar tudo ao agente, voz pt-BR e casa inteligente.
- [ ] Rodar E2E e validar Windows/Linux e modo offline.

## Fontes e licença da referência

- [README do Project NOMAD](https://github.com/Crosstalk-Solutions/project-nomad/blob/main/README.md)
- [LICENSE Apache-2.0](https://github.com/Crosstalk-Solutions/project-nomad/blob/main/LICENSE)
- [FAQ do Project NOMAD](https://github.com/Crosstalk-Solutions/project-nomad/blob/main/FAQ.md)

A matriz é uma auditoria inicial dos documentos públicos e do código do Optimus consultado. Ela não afirma que todos os recursos internos do NOMAD foram auditados em profundidade.
