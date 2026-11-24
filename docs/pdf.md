# Suite de documentos e PDF

O Optimus processa documentos localmente por meio de ferramentas do agente, CLI e API local.
A suite foi organizada para cobrir as categorias do iLovePDF sem depender de enviar documentos
a um serviço externo.

## Instalação

\`\`\`bash
pip install "optimus-assistente[pdf]"
\`\`\`

O extra instala pypdf, ReportLab, python-docx, Pillow, pypdfium2, pytesseract, pdfplumber, openpyxl, python-pptx e pyHanko.
OCR gera PDF pesquisável (texto invisível sobre as páginas renderizadas) e/ou TXT. PDF para Excel extrai tabelas quando detectáveis; PDF para PowerPoint cria slides com imagens das páginas. O editor adiciona elementos em coordenadas, sem edição livre do conteúdo existente. Também requer o executável Tesseract e os pacotes de idioma no sistema operacional.
Conversão Office/HTML para PDF requer LibreOffice. Alguns recursos avançados podem exigir
ferramentas externas específicas; o Optimus informa a dependência ausente em vez de simular
uma operação concluída.

## Ferramentas disponíveis

| Categoria | Ferramentas |
|---|---|
| Organizar | \`pdf_juntar\`, \`pdf_dividir\`, \`pdf_extrair\`, \`pdf_remover\`, \`pdf_organizar\`, \`pdf_girar\` |
| Otimizar | \`pdf_comprimir\`, \`pdf_reparar\`, \`pdf_ocr\` |
| Converter para PDF | \`pdf_imagens_para_pdf\` (JPG/PNG/TIFF/BMP), conversão Office e \`pdf_html_para_pdf\` via LibreOffice |
| Converter de PDF | \`pdf_converter\` (TXT/HTML/CSV/DOCX), \`pdf_para_imagens\` (JPG/PNG), \`pdf_para_markdown\` |
| Editar | \`pdf_cortar\`, \`pdf_marca\`, \`pdf_numeros\`, \`pdf_girar\` |
| Segurança | \`pdf_proteger\`, \`pdf_desbloquear\`, \`pdf_localizar_termos\`, \`pdf_censurar\` (bloqueada até haver redação segura) |
| Inteligência | \`pdf_comparar\`, \`pdf_resumir\`, \`pdf_formularios\`, \`pdf_metadados\` |

## Exemplos no chat

- "Junte contrato.pdf e anexo.pdf em um arquivo."
- "Converta estas fotos JPG em um PDF A4."
- "Extraia as páginas 2, 4 e 7 e salve como recortes.pdf."
- "Converta o PDF para imagens JPG e gere um ZIP."
- "Corte 20 pontos de cada margem das páginas 1 a 3."
- "Liste os campos preenchíveis deste formulário PDF."
- "Remova os metadados do documento e salve uma cópia."
- "Compare estes dois PDFs e mostre o que mudou."
- "Censure o CPF 123.456.789-00 no documento, gere uma cópia e informe as páginas afetadas."
- "Assine digitalmente contrato.pdf com certificado certificado.p12."
- "Converta o documento para PDF/A-2b usando meu perfil sRGB.icc."
- "Compare visualmente as duas versões e gere um ZIP das diferenças."
- "Preencha os campos do formulário PDF com os dados que informei."

## Terminal

As ferramentas registradas podem ser chamadas pelo agente. Os comandos diretos existentes incluem:

\`\`\`bash
optimus pdf info contrato.pdf
optimus pdf ler contrato.pdf --paginas 1-2
optimus pdf juntar a.pdf b.pdf --destino juntos.pdf
optimus pdf extrair contrato.pdf --paginas 2-4 --destino trecho.pdf
optimus pdf remover contrato.pdf --paginas 1
optimus pdf organizar contrato.pdf --paginas 3,1,2
optimus pdf dividir contrato.pdf --a-cada 1 --destino ./partes
optimus pdf girar contrato.pdf --graus 90
optimus pdf comprimir contrato.pdf
optimus pdf proteger contrato.pdf --senha segredo
optimus pdf desbloquear contrato.pdf --senha segredo
optimus pdf marca contrato.pdf --texto RASCUNHO
optimus pdf numeros contrato.pdf
optimus pdf comparar a.pdf b.pdf
optimus pdf ocr escaneado.pdf --idioma por
\`\`\`

## Limites técnicos e segurança

- \`pdf_assinar\` existente é um carimbo visual, não assinatura digital ICP-Brasil.
- \`pdf_censurar\` continua deliberadamente bloqueada: localizar texto ou desenhar tarja por cima
  não garante remoção irreversível de texto, imagens, OCR, camadas e anexos.
- A conversão de PDF para DOCX/HTML/CSV baseada em extração de texto não preserva perfeitamente
  a diagramação original. PDF para Office com fidelidade visual exige um motor especializado.
- \`pdf_comprimir\` com pypdf faz otimização estrutural; recompressão de imagens depende de
  ferramentas externas e pode reduzir qualidade.
- \`pdf_reparar\` é best-effort e não recupera bytes ou páginas já perdidos.
- `pdf_pdfa` usa Ghostscript com perfil ICC fornecido e política estrita de compatibilidade. A validação formal só é declarada quando veraPDF está instalado e aprova o arquivo; sem ele, o resultado fica marcado como não verificado.
- Formulários XFA, assinaturas digitais existentes e PDFs com conteúdo complexo podem ter
  limitações. O editor insere objetos sobre páginas, não é um editor livre de texto existente. O arquivo original é preservado e as saídas devem ser verificadas.
- Senhas e arquivos são processados localmente; não envie senhas para serviços de terceiros.

Consulte o resultado da ferramenta e valide o arquivo final antes de utilizá-lo oficialmente.
