# Estúdio de voz

O Optimus tem um estúdio completo para criar a voz dos seus vídeos: narrar textos, clonar a sua
voz, criar vozes novas por descrição, transcrever, legendar, traduzir e **dublar vídeos** (com uma
voz para cada pessoa), fazer **audiolivros**, **histórias e podcasts com várias vozes**, separar
a voz da música e **ditar em qualquer programa**. O **português do Brasil** é o idioma principal
em tudo, e há mais 17 idiomas.

Use pelo chat, pelo terminal ou pela tela **Estúdio de voz** do `optimus gui`.

Tudo roda no seu PC. A internet só é usada pelas vozes neurais online (Edge) e, se você quiser,
pelo modelo de IA na nuvem que faz a tradução.

## Instalar

```bash
pip install "optimus-assistente[estudio]"     # transcrição, legendas, dublagem, vozes, ffmpeg
pip install "optimus-assistente[clonagem]"    # clonar voz e conversor de voz (PyTorch, ~3 GB)
pip install "optimus-assistente[isolar]"      # separar voz da música (Demucs, PyTorch)
optimus estudio diagnostico                   # mostra o que está pronto e o que falta
```

Com placa de vídeo (NVIDIA ou Apple), clonagem e transcrição ficam muitas vezes mais rápidas.

## Pedindo ao Optimus

| Você diz | O que acontece |
|---|---|
| "Narra este texto com a voz Mordomo e salva em mp3" | Gera a narração em pt-BR |
| "Clona minha voz com o áudio gravacao.m4a" | Pede confirmação de consentimento e cria a voz |
| "Cria uma voz masculina grave e calma chamada Narrador" | Voz nova por descrição |
| "Transcreve a reuniao.mp4 em SRT" | Texto ou legenda com tempo |
| "Legenda o video.mp4 em inglês e queima no vídeo" | Legenda traduzida dentro da imagem |
| "Dubla o video.mp4 para português com a minha voz" | Dublagem completa, em segundo plano |
| "Dubla a entrevista com a voz original" | Clona quem fala no vídeo e dubla com a mesma voz |
| "Dubla o podcast com uma voz para cada pessoa e deixa só a música por baixo" | Elenco automático; a voz antiga sai, a música fica |
| "Transforma o livro.epub em audiolivro com a voz Mordomo" | Um MP3 por capítulo e um M4B com capítulos |
| "Faz um podcast com esse roteiro" | Uma voz para cada personagem, áudio único e legenda |
| "Separa a voz da música dessa música.mp3" | Arquivo só com a voz e outro só com a música |
| "Quem fala nessa entrevista?" | Quantas pessoas e quando cada uma fala |
| "Esse áudio é voz de IA?" | Procura a marca d'água do Optimus |
| "Como está a dublagem?" / "Cancela a dublagem" | Progresso e cancelamento |
| "O Kaik se fala Káique" | Dicionário de pronúncia para todas as vozes |
| "No projeto Canal, não traduza Optimus nem Minecraft" | Glossário da tradução |

## Pelo terminal

```bash
optimus estudio vozes
optimus estudio falar "Fala, pessoal! Bem-vindos ao canal." --voz Mordomo --saida intro.mp3
optimus estudio clonar "Minha voz" gravacao.m4a --consentimento
optimus estudio criar-voz Narradora feminina calma e grave
optimus estudio transcrever aula.mp4 --formato srt
optimus estudio traduzir aula.srt --idioma en-US
optimus estudio legendar video.mp4 --idioma pt-BR --legenda queimada
optimus estudio dublar video.mp4 --idioma pt-BR --voz "Minha voz" --legenda faixa
optimus estudio dublar entrevista.mp4 --voz-original --consentimento
optimus estudio dublar video.mp4 --legenda-pronta video.pt-BR.srt   # depois de revisar
optimus estudio converter locucao.wav --voz Nexus
optimus estudio pronuncia Kaik Káique
optimus estudio dublar podcast.mp4 --falantes --fundo musica
optimus estudio dublar podcast.mp4 --elenco "Pessoa 1=Nexus; Pessoa 2=Aurora"
optimus estudio legendar entrevista.mp4 --falantes          # "Pessoa 1: ..." na legenda
optimus estudio audiolivro livro.epub --voz Mordomo --autor "Fulano" --capa capa.jpg
optimus estudio historia roteiro.txt --elenco "Ana=Valkyrie; Bruno=Nexus"
optimus estudio separar musica.mp3
optimus estudio quem-fala entrevista.mp4
optimus estudio verificar-ia audio.mp3
optimus ditado                                               # botão flutuante de ditado
```

Os arquivos vão para a pasta de saídas do estúdio (`estudio.pasta_saidas` no `config.toml`).

## Vozes

- **Prontas:** Prime, Valkyrie, Nexus, Cyber, Stealth, Aurora, Lyra, Titan, Elite e a nova
  **Mordomo** (original do Optimus, calma e formal). Todas em português do Brasil.
- **Criadas por descrição:** o Optimus entende gênero, idade, tom (grave/aguda), ritmo
  (calma/animada), expressão (neutra/dramática) e efeitos (sussurro, robótica). Dá para partir
  de qualquer voz, inclusive de uma clonada, e ajustar depois (tom, velocidade, expressividade).
- **Clonadas:** de 10 a 30 segundos de fala limpa, sem música. Grave em português do Brasil
  para a voz sair com sotaque brasileiro, inclusive quando ela falar em outros idiomas.
- **Exportar e importar:** `.optimusvoz` leva a amostra, os ajustes e a declaração de
  consentimento para outro PC.

### Consentimento e marca de IA

Clonar exige declarar que **a voz é sua ou que você tem autorização da pessoa**. A declaração
fica gravada no perfil e o Optimus sempre pede confirmação antes de clonar. Todo áudio e vídeo
gerado leva a etiqueta "Voz gerada por IA (Open Optimus)" nos metadados **e uma marca d'água
inaudível** no próprio som: um padrão de cerca de 1 dB, espalhado entre 250 Hz e 7 kHz, que
sobrevive a MP3, AAC, OGG, mudança de volume e de taxa de amostragem. `optimus estudio
verificar-ia arquivo` diz se um áudio tem a marca (a pontuação acima de 4 significa que tem).

## Tela Estúdio de voz

No `optimus gui`, o menu **Estúdio de voz** tem abas para narrar (com player e download),
legendar e dublar (enviando o vídeo ou colando o caminho), vozes (criar, clonar com a
declaração, apagar), audiolivro, história e podcast, ferramentas (transcrever, separar voz,
quem fala, verificar IA, e o que está instalado), pronúncia e histórico com favoritos. As
tarefas longas aparecem embaixo com barra de progresso, cancelar e tentar de novo, e continuam
mesmo se você fechar a tela. A tela só abre arquivos das pastas do estúdio.

## Dublagem com várias pessoas

Com `--falantes` (ou "uma voz para cada pessoa"), o Optimus descobre quem fala quando
(diarização offline) e dá a cada pessoa uma voz diferente, ou a que você pedir no `--elenco`.
Com `--voz-original --falantes`, clona cada pessoa separadamente (com consentimento).
`--fundo musica` separa a voz antiga da música e dos efeitos (Demucs) e põe a voz nova por cima
só da música, como numa dublagem de verdade.

## Audiolivros

Aceita EPUB (na ordem do livro), PDF, DOCX, TXT, Markdown e HTML. Os capítulos são achados
sozinhos ("Capítulo 1", "CAPÍTULO II", "Chapter", "Prólogo", títulos `#`); sem títulos, o texto
é dividido em partes de tamanho parecido. Sai um MP3 por capítulo e um **M4B** com marcadores de
capítulo, título, autor e capa, que os apps de audiolivro entendem. Cada capítulo pronto fica
guardado: se parar, continua de onde parou.

## Histórias, podcasts e diálogos

Escreva uma fala por linha:

```text
Narrador: Era uma noite fria em São Paulo.
Ana: Você ouviu isso?
(pausa 1,5)
[Bruno] Foi só o vento.
E a cidade dormiu.
```

Cada personagem recebe uma voz diferente (ou a do `--elenco`); linhas sem nome ficam com o
narrador. Sai um áudio único e uma legenda `.srt` com o nome de quem fala.

## Ditado em qualquer programa

`optimus ditado` abre um botão 🎙 pequeno, sempre por cima das janelas. Clique, fale, e o texto
aparece onde o cursor estiver (Word, navegador, WhatsApp Web...). Fale a pontuação: "vírgula",
"ponto final", "ponto de interrogação", "dois pontos", "nova linha", "novo parágrafo", "abre
aspas", "fecha aspas". Arraste o botão para mudar de lugar; o botão direito fecha. No Windows,
clicar no botão não tira o cursor de onde você está escrevendo. Sem janela:
`optimus ditado --sem-janela`.

## Dublagem: como funciona

1. **Transcreve** o áudio (faster-whisper offline; sem ele, ou sem acesso ao Hugging Face, usa o
   sherpa-onnx com modelos baixados do GitHub) e divide em trechos legíveis.
2. **Traduz** com o modelo de IA do Optimus, em lotes numerados, respeitando o glossário e
   pedindo frases de tamanho parecido para caber no tempo. Para pt-BR, o pedido é explícito:
   português do Brasil, com vocabulário brasileiro.
3. **Fala** cada trecho com a voz escolhida (com o dicionário de pronúncia).
4. **Sincroniza:** se a fala passar do tempo, acelera até 35% sem mudar o tom.
5. **Junta** com o vídeo: o áudio original fica baixinho por baixo (`volume_original`, 0 para
   tirar) e a legenda entra como faixa ou queimada na imagem.

Cada etapa fica guardada: se a dublagem parar, ela recomeça de onde parou. Para revisar a
tradução antes, gere a legenda, edite o `.srt` e duble com `--legenda-pronta`.

## Idiomas

Português do Brasil, português de Portugal, inglês (EUA e Reino Unido), espanhol (Espanha e
latino), francês, alemão, italiano, japonês, chinês, coreano, russo, árabe, hindi, holandês,
polonês e turco.

## Para outros programas (API compatível com a OpenAI)

Com `optimus gui` aberto, qualquer programa que fala com a API de áudio da OpenAI pode usar as
vozes e a transcrição do Optimus. Aponte para `http://127.0.0.1:8765/v1`:

```bash
curl http://127.0.0.1:8765/v1/audio/speech -H "Content-Type: application/json" \
  -d '{"input": "Olá!", "voice": "Mordomo", "response_format": "mp3"}' -o ola.mp3
curl http://127.0.0.1:8765/v1/audio/transcriptions -F file=@aula.mp3 -F response_format=srt
```

Com senha (`web.senha`), mande `Authorization: Bearer SUA_SENHA`. Os nomes de voz da OpenAI
(alloy, onyx, nova...) são aceitos e viram vozes do Optimus.

## Motores e licenças

| Função | Motor | Licença |
|---|---|---|
| Vozes pt-BR offline | Kokoro (ONNX) | Apache-2.0 |
| Vozes online em 18 idiomas | Microsoft Edge (neural) | serviço online gratuito |
| Clonagem e conversor de voz | Chatterbox Multilingual | MIT |
| Transcrição | faster-whisper | MIT |
| Transcrição reserva (modelos do GitHub) e quem fala quando | sherpa-onnx (Whisper ONNX, Silero VAD, pyannote 3.0, CAM++) | Apache-2.0 / MIT |
| Separar voz da música | Demucs (htdemucs) | MIT |
| PDF para audiolivro | pypdf | BSD |
| Marca d'água | código próprio (numpy) | do Optimus |
| Áudio e vídeo | ffmpeg (imageio-ffmpeg) | LGPL/GPL, programa separado |

O estúdio foi escrito do zero para o Optimus; nenhum código de outros estúdios de voz foi
copiado.
