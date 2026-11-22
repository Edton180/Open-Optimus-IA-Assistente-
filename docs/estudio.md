# Estúdio de voz

O Optimus tem um estúdio completo para criar a voz dos seus vídeos: narrar textos, clonar a sua
voz, criar vozes novas por descrição, transcrever, legendar, traduzir e **dublar vídeos**. O
**português do Brasil** é o idioma principal em tudo, e há mais 17 idiomas.

Tudo roda no seu PC. A internet só é usada pelas vozes neurais online (Edge) e, se você quiser,
pelo modelo de IA na nuvem que faz a tradução.

## Instalar

```bash
pip install "optimus-assistente[estudio]"     # transcrição, legendas, dublagem, vozes, ffmpeg
pip install "optimus-assistente[clonagem]"    # clonar voz e conversor de voz (PyTorch, ~3 GB)
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
gerado leva a etiqueta "Voz gerada por IA (Open Optimus)" nos metadados.

## Dublagem: como funciona

1. **Transcreve** o áudio (faster-whisper, offline) e divide em trechos legíveis.
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
| Áudio e vídeo | ffmpeg (imageio-ffmpeg) | LGPL/GPL, programa separado |

O estúdio foi escrito do zero para o Optimus; nenhum código de outros estúdios de voz foi
copiado.
