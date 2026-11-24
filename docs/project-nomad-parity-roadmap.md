# Plano de paridade funcional com o Project NOMAD

Este documento transforma a referência pública do Project NOMAD em requisitos verificáveis para o Optimus. O objetivo é alcançar e superar a experiência e a cobertura funcional, sem copiar código, marcas, imagens ou ativos protegidos do projeto de referência.

**Regra de conclusão:** um recurso só muda para concluído quando frontend, API/backend, persistência local, tratamento de erros, documentação e testes automatizados estiverem implementados. Uma tela, botão ou integração simulada não conta como funcional.

## Inventário de capacidades da referência

| Capacidade | Experiência esperada no Optimus | Situação a validar/implementar |
|---|---|---|
| Biblioteca offline (Kiwix) | Catálogo de arquivos ZIM, leitor sob demanda, importação/atualização e pesquisa por conteúdo | Em evolução: leitor e catálogo existentes; indexação incremental e RAG local no PR #75 |
| Base de conhecimento de IA | Conversa local com documentos e coleções offline, recuperação lexical/semântica e citações rastreáveis | Parcial: biblioteca de documentos existente; RAG ZIM em implementação; unificar fontes e filtros |
| Educação (Kolibri) | Cursos offline, catálogo, usuários, matrícula, aulas, avaliações e progresso | Pendente: integração gerenciada e experiência de aprendizagem no Optimus |
| Mapas offline (ProtoMaps) | Catálogo por região, download/importação, visualização e pesquisa sem internet | Pendente |
| Ferramentas de dados (CyberChef) | Transformações de texto/arquivos, codificação, hashes, compressão e análise em interface visual | Parcial: laboratório local tem operações básicas; ampliar catálogo e testes |
| Notas (FlatNotes) | Criar, editar, organizar, pesquisar e exportar notas locais | Pendente como módulo integrado completo |
| Benchmark do sistema | Testes reproduzíveis de CPU, memória, armazenamento e IA; histórico e recomendações compatíveis com o hardware | Pendente |
| Catálogo de aplicativos (Supply Depot) | Catálogo curado, instalação/atualização/remoção, estado, logs, backups e opção para serviços próprios | Parcial: Central de módulos e gerenciador Home Assistant; falta catálogo extensível |
| Assistente de configuração | Configuração inicial guiada, seleção de coleções e verificação de dependências | Pendente |
| Curadoria de conteúdo | Seleção de Wikipedia/coleções, tamanhos, idiomas, fontes e atualização do conteúdo | Pendente além do fluxo manual de arquivos ZIM |
| Atualizações | Atualização verificável do núcleo, módulos e conteúdos, com backup, rollback e status claro | Parcial: atualizador do núcleo existe; revisar distribuição, recuperação e atualização dos módulos/conteúdos |

## Requisitos transversais obrigatórios

1. **Offline-first real:** depois de instalados os componentes e baixados os conteúdos, as funções de leitura, busca, cursos, mapas, notas e ferramentas locais devem operar sem internet. A internet só pode ser necessária para obter novos conteúdos, atualizações ou serviços externos explicitamente escolhidos.
2. **Dados locais:** documentos, ZIMs, notas, progresso de cursos, configurações, tokens e índices permanecem em diretórios locais do Optimus. Nunca enviar arquivos pessoais para serviços remotos por padrão.
3. **Instalação gerenciada:** cada integração deve declarar dependências, espaço em disco, memória, sistemas suportados, permissões e estratégia de atualização/remoção. Preservar dados ao atualizar/remover containers.
4. **Frontend ligado ao backend:** nenhum botão decorativo; todas as ações devem ter endpoint, validação, estado de progresso, cancelamento quando aplicável e erro legível.
5. **Compatibilidade de API:** manter testes de contrato para cada rota consumida pelo frontend. Se a API instalada não suportar uma função, mostrar diagnóstico com versão/API incompatível, sem apresentar falso sucesso.
6. **Segurança:** credenciais mascaradas e guardadas localmente; serviços locais limitados ao loopback por padrão; operações administrativas pedem autorização; nunca encerrar processos de terceiros.
7. **Hardware adaptativo:** no perfil leve (2 núcleos/4 threads e cerca de 7 GB de RAM), serviços pesados não iniciam automaticamente. Downloads e indexações são explícitos, em lotes, retomáveis e com limites de memória/CPU. Serviços opcionais podem ser instalados sob demanda.
8. **Acessibilidade e recuperação:** interface em português brasileiro, responsiva, com estados vazios, carregamento, erro, logs e instruções de recuperação.

## Ordem recomendada de entrega

### Etapa 1 — Confiabilidade do núcleo (bloqueador)
- Corrigir a divergência entre assets do frontend e versão da API que causou respostas 404 rota não encontrada.
- Testar rotas ZIM e Casa inteligente por HTTP real, incluindo GET/POST, erros e instalação gerenciada.
- Garantir que atualização substitua o backend e frontend juntos, reinicie corretamente e apresente a versão/commit efetivamente carregados.
- Rodar Playwright sem mocks para verificar contratos locais; manter mocks apenas para cenários de falha.

### Etapa 2 — Conhecimento offline completo
- Concluir indexação ZIM incremental, pesquisa unificada ZIM + documentos, recuperação híbrida e RAG com fontes.
- Adicionar catálogo/curadoria de coleções, idiomas, tamanho estimado, origem e instruções de atualização.
- Tornar a ingestão de novos formatos modular, sem bloquear o chat durante indexações.

### Etapa 3 — Educação e produtividade offline
- Integrar Kolibri como serviço gerenciado opcional, com catálogo de cursos, autenticação, progresso e retorno ao painel do Optimus.
- Implementar notas locais e ferramentas de dados ampliadas.
- Criar onboarding para instalação e importação de conteúdos.

### Etapa 4 — Mapas e ecossistema de módulos
- Integrar mapas offline por região e busca local.
- Criar catálogo de aplicativos/serviços com instalação, status, logs, backup, atualização e remoção segura.
- Padronizar contratos e adaptadores para novas integrações.

### Etapa 5 — Benchmark e otimização
- Implementar benchmark reproduzível e recomendações de perfil.
- Validar consumo real em Windows e Linux, incluindo máquinas sem GPU dedicada.
- Só habilitar recursos pesados quando o usuário optar por instalá-los.

## Critérios de aceite por módulo

- Teste unitário de lógica e persistência.
- Teste de API cobrindo todas as rotas usadas pela interface.
- E2E Playwright cobrindo os fluxos principais e verificando erros de console, exceções e respostas HTTP inesperadas.
- Teste de instalação/atualização/remoção em ambiente suportado, com preservação de dados.
- Teste offline após a instalação e download dos conteúdos.
- Documentação de requisitos, limites, permissões, consumo estimado e recuperação.

Este roadmap é uma especificação de trabalho, não uma declaração de que todos os módulos já existem. Cada etapa deve ser entregue e validada separadamente antes de ser anunciada como concluída.
