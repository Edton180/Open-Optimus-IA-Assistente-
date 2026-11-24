# Leitor local de bibliotecas ZIM

O Optimus pode abrir arquivos `.zim` da pasta gerenciada usando o executável opcional
`kiwix-serve` (pacote Kiwix Tools). A integração é independente do Project NOMAD e não
incorpora código, imagens ou dependências dele.

## Preparação

1. Instale o Kiwix Tools apropriado ao seu sistema operacional.
2. Garanta que o executável `kiwix-serve` esteja disponível no `PATH` do processo que inicia o Optimus.
3. Coloque os arquivos `.zim` em `biblioteca_zim`, dentro da pasta de dados do Optimus.
4. Abra **Conhecimento offline (ZIM)**, atualize a biblioteca, selecione um arquivo e clique em **Abrir leitura**.
5. Clique no link apresentado para abrir o leitor no navegador.

Se o executável não for encontrado, o Optimus informa que o recurso está indisponível. Não há download ou instalação silenciosa.

## Segurança e ciclo de vida

- O servidor é iniciado somente após ação explícita do usuário.
- O processo recebe argumentos separados, sem shell ou interpolação de comandos.
- O arquivo deve ser um arquivo regular `.zim` dentro da biblioteca gerenciada; caminhos externos, travessia de diretórios e links simbólicos são rejeitados.
- O Kiwix escuta somente em `127.0.0.1:8767`, não na rede local nem na internet.
- O botão **Fechar leitor** encerra somente o processo criado por esta instância do Optimus. Outros processos Kiwix não são localizados nem encerrados.
- O Optimus também encerra o processo gerenciado ao fechar normalmente (saída graciosa). Encerramento forçado do sistema operacional pode impedir essa limpeza.
- Se o Kiwix terminar inesperadamente, atualize a biblioteca para atualizar o estado.
- A porta 8767 precisa estar livre. O Optimus não tenta encerrar um serviço de terceiros que esteja usando essa porta.

## Limitações desta etapa

Esta etapa entrega abertura/leitura pelo Kiwix. Ainda não oferece pesquisa de texto unificada entre ZIMs, indexação vetorial ou respostas RAG com citações. Essas funções serão implementadas separadamente, preservando a origem (arquivo, artigo e URL) de cada trecho recuperado.

O software Kiwix e cada arquivo ZIM têm licenças próprias. Verifique as condições de redistribuição do executável e do conteúdo que você adicionar.
