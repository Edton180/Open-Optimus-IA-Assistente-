# Biblioteca ZIM offline

O Optimus mantém uma pasta gerenciada para bibliotecas offline no formato ZIM:

- Linux: dentro do diretório de dados configurado pelo Optimus, em `biblioteca_zim/`.
- Windows: no mesmo diretório de dados do perfil do Optimus, em `biblioteca_zim\`.

A API local `GET /api/zim` lista arquivos `.zim` regulares dessa pasta, com nome, tamanho e data de modificação. Links simbólicos, subpastas e outros formatos são ignorados.

## Escopo desta etapa

Esta implementação é somente um catálogo local. Não baixa arquivos, não extrai conteúdo, não inicia processos Kiwix e não acessa automaticamente pastas externas. O servidor Kiwix e a leitura/indexação do conteúdo serão etapas separadas, com controles explícitos e validação própria.

Os arquivos ZIM e os conteúdos que eles distribuem continuam sujeitos às licenças e condições dos respectivos produtores.
