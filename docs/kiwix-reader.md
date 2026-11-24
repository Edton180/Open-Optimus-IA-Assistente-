# Kiwix Tools e biblioteca ZIM gerenciados

O Optimus pode instalar Kiwix Tools no diretório privado de dados do aplicativo,
abrir ZIMs locais e consultar o índice textual interno dos arquivos que o possuem.
A instalação é iniciada explicitamente pelo usuário na tela **Conhecimento offline**.

## Instalação gerenciada

- O Optimus detecta sistema operacional e arquitetura e seleciona um pacote oficial compatível.
- O download é feito por HTTPS da distribuição oficial Kiwix, limitado a 100 MiB.
- A extração rejeita caminhos de travessia e não materializa links, dispositivos ou FIFOs.
- Os binários ficam dentro de `<dados-do-Optimus>/tools/kiwix-tools`; não altera PATH global, registro, pacotes do sistema ou permissões administrativas.
- A versão atualmente fixada no adaptador é Kiwix Tools 3.8.2.
- Plataformas mapeadas: Windows x86_64, Linux x86_64/aarch64 e macOS x86_64/arm64. Outras arquiteturas recebem uma mensagem explícita de incompatibilidade.
- O instalador registra o SHA-256 calculado do pacote baixado para diagnóstico. Esse hash local não é uma assinatura nem um checksum publicado pelo upstream.
- O pacote e a licença upstream continuam sendo de responsabilidade do projeto Kiwix; consulte https://github.com/kiwix/kiwix-tools.

## Leitura e isolamento

1. Coloque arquivos `.zim` legítimos em `biblioteca_zim`, na pasta de dados do Optimus.
2. Abra **Conhecimento offline**, atualize o catálogo e selecione um arquivo.
3. Clique em **Abrir leitura**. O servidor escuta somente em `127.0.0.1`.
4. Clique em **Fechar leitor** para encerrar o processo iniciado por esta instância.

O Optimus nunca procura processos Kiwix de terceiros para encerrá-los. Usa a referência do
processo criado por `subprocess.Popen` nesta instância; não mata processo por nome nem por
porta. Se a porta estiver ocupada, a inicialização falha com aviso e não interfere no serviço
que já está escutando. O servidor também é encerrado em saída graciosa do Optimus.

## Busca e citações

A busca da tela combina:
- **ZIM:** endpoint público `/search` do `kiwix-serve`, em formato XML, para cada arquivo que
  contém índice de texto completo. A consulta é feita localmente e os resultados incluem nome
  do ZIM, título, trecho retornado e URL local.
- **Documentos:** pesquisa textual SQLite FTS5 da biblioteca existente, com título, caminho e
  trecho de origem.

A busca não indexa conteúdo ZIM por conta própria. Arquivos sem índice de texto completo não
retornam resultados de texto. Consultas em múltiplos ZIMs são feitas individualmente para não
misturar idiomas incompatíveis. Se o leitor já estiver aberto para outro arquivo, a busca não
o interrompe: informa que o usuário deve fechar o leitor ou limitar a pesquisa ao arquivo ativo.

## O que ainda não está implementado

- Indexação incremental própria do conteúdo ZIM e extração completa de artigos.
- Índice vetorial e recuperação híbrida.
- RAG integrado ao agente, com citações verificadas de artigo, arquivo, URL interna e trecho.
- Atualização automática do Kiwix Tools e assinatura criptográfica do pacote.

Esses itens continuam pendentes na trilha de Knowledge Center/RAG. Não anunciar a busca atual
como RAG ou busca semântica: ela é uma busca textual apoiada nos índices dos ZIMs e no FTS5
dos documentos.

## Licenças e Project NOMAD

Nenhum código do Project NOMAD foi copiado. O README/licença Apache-2.0 do NOMAD foi consultado
apenas para entender o escopo público do projeto. O Kiwix Tools e cada ZIM têm licenças próprias;
confira a origem, licença, idioma e condições de redistribuição de cada conteúdo.
