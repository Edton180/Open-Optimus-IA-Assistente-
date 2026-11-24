# Biblioteca ZIM offline

O Optimus mantém uma pasta gerenciada para bibliotecas offline no formato ZIM:

- Linux: dentro do diretório de dados configurado pelo Optimus, em `biblioteca_zim/`.
- Windows: no mesmo diretório de dados do perfil do Optimus, em `biblioteca_zim\`.

A API local `GET /api/zim` lista arquivos `.zim` regulares dessa pasta, com nome, tamanho e data de modificação. Links simbólicos, subpastas e outros formatos são ignorados.

## Conteúdo inicial do Project NOMAD

Na primeira abertura da tela, se a biblioteca estiver vazia, o Optimus tenta obter automaticamente o arquivo inicial (4,5 MB), como faz o pré-install do Kiwix no NOMAD. A tela informa o progresso; se a rede estiver indisponível, o botão **Adicionar conteúdo inicial do Project NOMAD** permite tentar novamente. O arquivo `wikipedia_en_100_mini_2026-01.zim` usado pelo pré-install oficial do Kiwix no NOMAD. O download é feito para uma pasta temporária, validado pelo tamanho e pelo Git blob SHA-1 publicado pelo GitHub e movido atomicamente para a biblioteca. Um arquivo já existente nunca é substituído. O processo não instala nem inicia o Kiwix.

O repositório de referência também mantém uma versão mini anterior (`2025-06`), mas o instalador atual do NOMAD utiliza `2026-01`; por isso, o Optimus importa apenas a versão efetivamente selecionada pelo pré-install atual, evitando duplicar a mesma mini-Wikipédia. As coleções maiores do NOMAD são catálogos de downloads opcionais, não arquivos pré-instalados.

## Escopo desta etapa

O catálogo local lista os arquivos presentes na pasta gerenciada. O conteúdo inicial é obtido por uma ação explícita; não há download silencioso, não há extração automática nem inicialização do Kiwix. A leitura e a indexação do conteúdo são etapas separadas, com controles explícitos e validação própria.

Os arquivos ZIM e os conteúdos que eles distribuem continuam sujeitos às licenças e condições dos respectivos produtores.
