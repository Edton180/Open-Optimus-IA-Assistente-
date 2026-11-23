# PDF

O Optimus junta, divide, gira, protege, converte e lê PDF no chat, no terminal e na tela
`/pdf.html` do `optimus gui`.

```bash
pip install "optimus-assistente[pdf]"
```

Isso instala o pypdf e o Pillow. OCR e PDF virado imagem pedem extras à parte
(`pypdfium2`, `pytesseract` + o programa Tesseract). Word, PowerPoint e Excel **para** PDF
usam o LibreOffice (`soffice`), se estiver instalado.

## Terminal

```bash
optimus pdf info contrato.pdf
optimus pdf ler contrato.pdf --paginas 1-2
optimus pdf juntar a.pdf b.pdf --destino juntos.pdf
optimus pdf extrair contrato.pdf --paginas 2-4 --destino trecho.pdf
optimus pdf remover contrato.pdf --paginas 1
optimus pdf organizar contrato.pdf --paginas 3,1,2
optimus pdf dividir contrato.pdf --a-cada 1 --destino ./partes
optimus pdf girar contrato.pdf --graus 90
optimus pdf cortar contrato.pdf --margem 36
optimus pdf comprimir contrato.pdf
optimus pdf reparar quebrado.pdf
optimus pdf proteger contrato.pdf --senha segredo
optimus pdf desbloquear contrato.pdf --senha segredo
optimus pdf marca contrato.pdf --texto RASCUNHO
optimus pdf numeros contrato.pdf
optimus pdf assinar contrato.pdf --texto "Edton Braz"
optimus pdf censurar contrato.pdf --texto "CPF,senha"
optimus pdf comparar a.pdf b.pdf
optimus pdf html contrato.pdf
optimus pdf docx contrato.pdf
optimus pdf csv contrato.pdf
optimus pdf ocr escaneado.pdf --idioma por
```

## Chat

Diga o que quer: "junta estes PDFs", "tira a página 2", "resume este PDF", "traduz o texto".
As ferramentas são `pdf_juntar`, `pdf_extrair`, `pdf_ler`, `pdf_resumir`, `pdf_converter`,
`pdf_ocr` e as outras do grupo `pdf`. O resumo e a tradução ficam com o modelo do Optimus:
`pdf_resumir` só entrega o texto.

## Limites honestos

- **Assinatura** é um carimbo visual com o nome. Não é certificado ICP-Brasil.
- **Censura** localiza os termos e marca o arquivo. Não desenha tarja preta em cima de cada palavra.
- **PDF/A** certificado precisa do Ghostscript (`gs -dPDFA`). Sem ele, o Optimus só regrava o arquivo e avisa.
- **PDF escaneado** não tem texto até o OCR. Sem Tesseract, `pdf_ler` devolve vazio e pede o OCR.
- **PowerPoint e Excel para PDF** dependem do LibreOffice. No sentido contrário, o Optimus extrai o texto para HTML, DOCX ou CSV.
