# Indexação incremental e RAG local para ZIM

O Optimus lê artigos diretamente dos arquivos ZIM com a biblioteca oficial
[python-libzim](https://github.com/openzim/python-libzim). Instale o extra opcional:

```bash
pip install "optimus-assistente[conhecimento]"
```

A dependência publica wheels para Windows x64, Linux x86_64/aarch64 e macOS
x86_64/arm64. Para Python 3.11 ou superior, o Optimus usa libzim 4.1+; no Python
3.10, usa a linha 3.13.x, que mantém compatibilidade com essa versão do Python. O
adaptador usa o iterador eficiente novo ou o acesso por ID da API anterior. O conteúdo permanece local. Se a dependência não estiver disponível, o botão de indexação
instala automaticamente o wheel oficial em uma pasta privada do Optimus usando o Python
atual; não altera PATH, não usa privilégios administrativos e não modifica o ambiente global.

## Indexação incremental

Na tela **Conhecimento offline**, use **Indexar / continuar**. Cada execução processa
no máximo 150 entradas (limite configurável pela API, até 1.000), registra o cursor e
retoma de onde parou. O estado do arquivo considera tamanho e mtime; quando o arquivo
ZIM muda, os trechos antigos daquele arquivo são removidos e a indexação recomeça.
Artigos são extraídos em memória com limite de 2 MiB, HTML é convertido em texto e
dividido em chunks com sobreposição. SQLite FTS5 guarda o índice lexical e a origem
exata de cada trecho. Não altera o arquivo ZIM.

## Recuperação híbrida e embeddings

A recuperação combina cobertura lexical FTS5 com similaridade cosseno de embeddings.
Se um modelo de embedding compatível já estiver instalado no Ollama, o Optimus detecta
automaticamente modelos conhecidos (EmbeddingGemma, nomic-embed-text, mxbai-embed-large,
BGE-M3, Snowflake Arctic Embed e all-minilm). Também aceita o nome explícito via API.
Nenhum modelo de embedding é baixado silenciosamente. Se houver um modelo conhecido já instalado,
o Optimus o detecta; se o modelo for instalado posteriormente, os embeddings ausentes podem
ser preenchidos sem reler os artigos ZIM. Sem um modelo local, a recuperação continua
funcionando em modo lexical e a interface deve identificar que não há vetores.

## RAG conectado ao agente

Antes de responder, o agente consulta o índice local para a pergunta atual e injeta
até cinco evidências no contexto. Cada trecho contém título, arquivo ZIM, caminho do
artigo e URI `zim://arquivo.zim/caminho`. O prompt exige citações `[Fonte ZIM N]`
e proíbe inventar referências. Conteúdo recuperado é tratado como dado não confiável,
nunca como instrução.

## Endpoints locais

- `GET /api/zim/status`: contagem de artigos, trechos e embeddings.
- `POST /api/zim/indexar`: processa um lote; JSON opcional `{"limite":150,"modelo_embedding":"nome"}`.
- `GET /api/zim/rag?q=...`: recuperação híbrida/lexical.
- A busca textual Kiwix anterior permanece disponível em `GET /api/zim/buscar`.

## Limites honestos

- A primeira indexação de uma coleção grande pode demorar; execute em lotes e deixe o
  processo retomar entre sessões.
- A comparação de hash por trecho evita regravar conteúdo idêntico, mas uma substituição
  do arquivo ZIM reinicia o índice desse arquivo.
- A busca vetorial é ativada somente quando um modelo de embedding local está instalado
  e responde ao endpoint Ollama. Caso contrário, o sistema não finge que a busca lexical
  é semântica.
- Imagens, áudio, vídeo, scripts executáveis e anexos binários não são indexados como texto.
- As citações apontam para o artigo e trecho local; a interface de leitura Kiwix pode ser
  usada para abrir o artigo quando o leitor estiver iniciado.
