# Integração do Optimus com OpenOffice e LibreOffice

## O que é integrado

O Optimus usa a interface de linha de comando `soffice`, fornecida pelo LibreOffice e também disponível em instalações compatíveis do Apache OpenOffice, como mecanismo local para abrir e converter documentos. A integração permite:

- Converter DOC, DOCX, XLS, XLSX, PPT, PPTX, ODT, ODS, ODP, RTF, TXT e CSV para PDF pela Central **Documentos e PDF**.
- Unir PDFs, imagens e documentos Office em um único PDF, respeitando a ordem dos arquivos.
- Processar documentos no computador que executa o Optimus; ao usar o painel remotamente, os arquivos trafegam pela conexão HTTPS até esse computador.

**Importante:** o mecanismo atualmente implementado é a automação de documentos via `soffice`. Isso não significa que exista, nesta versão, uma barra lateral ou extensão nativa do Optimus dentro da janela do Writer, Calc ou Impress. Não confunda conversão/abertura integrada com um complemento de interface ainda não entregue.

## Instalação automática

Os instaladores do Optimus tentam detectar uma suíte compatível e instalar o LibreOffice quando ele não está presente:

- Windows 10/11: winget, pacote `TheDocumentFoundation.LibreOffice`.
- Ubuntu/Debian/Mint: APT, pacote `libreoffice`.
- Fedora: DNF, pacote `libreoffice`.
- Arch: pacman, pacote `libreoffice-fresh`.
- macOS: Homebrew Cask, pacote `libreoffice`.

A instalação da suíte pode solicitar privilégios administrativos. Se o gerenciador de pacotes não estiver disponível, a instalação automática falhar ou a rede bloquear o download, o instalador informa isso; não declara a integração pronta. Nessa situação, instale o LibreOffice pelo gerenciador oficial do sistema e execute novamente o diagnóstico do Optimus.

## Como conferir

1. Abra o Optimus e entre em **Documentos e PDF**.
2. Adicione um arquivo DOCX, XLSX, PPTX ou ODT.
3. Escolha a ferramenta **Documento para PDF**.
4. Execute e confira o PDF gerado na área de resultados.
5. Se o Optimus informar que não encontrou `soffice`, verifique se o LibreOffice foi instalado e se o executável está no PATH.

No terminal, o comando de verificação é:

```bash
soffice --version
```

Em algumas distribuições, o nome alternativo é `libreoffice --version`.

## Configuração e solução de problemas

- **Windows:** feche e reabra o Optimus após a instalação para atualizar o PATH. Se necessário, verifique o caminho do LibreOffice em `C:\Program Files\LibreOffice\program\soffice.exe`.
- **Linux:** confirme a instalação com `which soffice` e `soffice --version`.
- **macOS:** confirme que o aplicativo LibreOffice está instalado em Applications e que `soffice` está acessível no PATH.
- **Falha por arquivo aberto:** feche o documento no Writer/Calc/Impress e tente novamente; o Optimus cria um perfil temporário isolado para conversão.
- **Layout diferente:** fontes ausentes, macros, fórmulas avançadas e recursos proprietários podem alterar a aparência. Instale as fontes necessárias e confira o resultado.
- **Arquivo protegido ou corrompido:** desbloqueie ou repare o documento no aplicativo de origem antes da conversão.

## Segurança e limites

- A conversão é executada localmente com processo separado e tempo limite.
- O Optimus não envia o conteúdo a um serviço de conversão externo.
- Macros de documentos não são executadas deliberadamente pelo fluxo de conversão.
- A conversão não garante fidelidade perfeita entre formatos proprietários e abertos; sempre revise o PDF final.
- Recursos avançados do PDF podem exigir dependências adicionais descritas em [pdf.md](pdf.md).

## O que ainda não deve ser anunciado como pronto

Uma extensão nativa com barra de ferramentas e comandos do Optimus dentro das janelas Writer, Calc e Impress é uma etapa separada. Até que essa extensão tenha instalador, chamadas autenticadas, ações de seleção/documento, interface e testes próprios, a interface do Optimus não deve afirmar que o assistente está embutido no OpenOffice.
