# Catálogo de conhecimento offline (ZIM)

O Optimus mantém um catálogo versionado das coleções ZIM do Project NOMAD em
`optimus/catalogo/zim-nomad.json`. Ele inclui as categorias e os níveis
Essential, Standard e Comprehensive, além das opções de Wikipedia.

## O que fica no GitHub

- Manifesto JSON, nomes, descrições, versões, tamanhos estimados, URLs e categorias.
- Código do Optimus para apresentar o catálogo e reconhecer arquivos já presentes.
- Não são armazenados no Git os arquivos binários `.zim`; eles podem ter vários GB
  e permanecem sob as licenças e condições dos respectivos produtores.

## Catálogo na interface

A tela **Conhecimento offline (ZIM)** apresenta todas as coleções do manifesto,
seus níveis e recursos, mesmo que nenhum arquivo tenha sido baixado. Um recurso
só aparece como instalado quando o arquivo correspondente existe como arquivo
regular na pasta gerenciada `biblioteca_zim`.

O catálogo não instala automaticamente os níveis Standard ou Comprehensive.
Os níveis Essential são destacados como recomendados. O arquivo inicial
`wikipedia_en_100_mini_2026-01.zim` continua sendo obtido pelo mecanismo de
primeira inicialização já existente, com validação de integridade.

## Atualização e procedência

O manifesto é uma cópia de metadados dos catálogos públicos do repositório
`Crosstalk-Solutions/project-nomad`. Para atualizar, revise as alterações no
catálogo upstream, atualize o JSON versionado e confira URLs, tamanhos e
licenças antes de publicar. O Optimus não copia o código-fonte do NOMAD.
