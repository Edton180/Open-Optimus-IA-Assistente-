# Voz

## Conversar por voz

**Terminal:** `optimus voz`. Diga **"Optimus, ..."** e o pedido. Depois da resposta, por 25 segundos você
pode continuar falando sem repetir o nome (modo conversa). "Pode parar" ou "tchau" encerram o modo
conversa. Ctrl+C sai.

**Interface, ao vivo (recomendado):** clique em **🎙️ Ao vivo** (ou no orbe) e libere o microfone.

- Diga **"Optimus, ..."** e o pedido. Por 25 segundos depois de cada resposta, não precisa repetir o nome.
- **Duas palmas** chamam o Optimus ("Às ordens").
- Ele fala a resposta **frase por frase enquanto ela ainda está sendo escrita**, então começa a falar
  em poucos segundos e fala a resposta inteira.
- Para interromper: diga **"pare"** ou **"Optimus"**, clique no orbe ou no botão **■ Parar**.
- Confirmações podem ser respondidas falando ("sim", "não", "confirmo").

O reconhecimento usa o do navegador (Chrome e Edge, precisa de internet) e, se ele não estiver
disponível, o **Whisper no próprio PC** (`pip install faster-whisper`), detectando quando você começa e
termina de falar. A fala usa a voz escolhida; se ela falhar, o navegador fala com a voz dele, para nunca
ficar mudo. O microfone só funciona em `http://localhost` ou em HTTPS (regra dos navegadores): no
celular pela rede, use a voz do teclado ou configure HTTPS.

**Interface, um pedido:** clique no 🎙️ da caixa de texto, fale, e ele envia quando você parar.
O botão 🔈/🔊 liga a leitura das respostas digitadas.

Ações que precisam de confirmação são perguntadas em voz alta. Responda "sim" (ou "pode") nas moderadas
e **"confirmo"** nas críticas. Qualquer "não", "espera" ou "cancela" nega, mesmo junto de um "sim".

## Vozes prontas

| Voz | Gênero | Tipo | Precisa de |
|---|---|---|---|
| **Prime** | masculina | natural, offline (Kokoro) | arquivos de voz (o instalador baixa) |
| **Valkyrie** | feminina | natural, offline (padrão) | idem |
| **Nexus** | masculina, grave | natural, offline | idem |
| **Cyber** | masculina robótica | offline, com efeito de rádio | idem + numpy |
| **Stealth** | feminina, baixa e abafada | offline, com efeito | idem + numpy |
| **Elite** | masculina, cinematográfica | ElevenLabs (online) | chave da ElevenLabs em `voz.elevenlabs_chave` |
| **Edton Braz** | masculina | brasileira, jovem, simpática e animada (ElevenLabs) | chave da ElevenLabs em `voz.elevenlabs_chave` |
| Aurora, Lyra, Titan | fem., fem., masc. | neural, online (Edge) | internet |
| Sistema (feminina/masculina) | ambos | voz do Windows (Maria, Daniel), espeak-ng no Linux, voz do Android | nada |

A opção **Edton Braz** atualmente aponta para uma voz pública da biblioteca ElevenLabs identificada no código como “Matheus - Friendly and Energetic”. Ela **não é uma clonagem validada da voz pessoal do Edton** e não foi comparada automaticamente com uma amostra de referência. Sem chave ElevenLabs, o sistema usa uma voz masculina de reserva (Titan/Prime), que não é a mesma voz.

Para ajustar a voz à amostra pessoal, é necessário importar novamente o áudio de referência no Estúdio e fazer uma avaliação auditiva consentida. A auditoria do histórico disponível não localizou o arquivo de áudio original; portanto, nenhuma semelhança com ele pode ser afirmada neste momento.

Troque falando: *"Optimus, mude para a voz Edton Braz"* ou *"mude para a voz Matheus"*. Se a voz escolhida não estiver disponível, ele usa a reserva mais parecida e avisa.

Escolha em **Configurações > Voz** (botão ▶ Ouvir para testar) ou:

```bash
optimus vozes                      # lista e mostra quais estão prontas
optimus config voz.voz masculina   # melhor voz masculina disponível
optimus config voz.voz feminina
optimus config voz.voz edton-braz
optimus config voz.voz edge:pt-BR-AntonioNeural
optimus config voz.velocidade 1.15
optimus vozes --testar
```

Com `feminina` ou `masculina`, o Optimus usa a voz offline natural se estiver instalada; senão, a online
(se houver internet); senão, a do sistema. Sem internet a voz online cai para a offline sozinha.

## Reconhecimento de voz

Offline, com o **faster-whisper**. O tamanho do modelo vem do perfil do PC (tiny, base, small,
large-v3-turbo) e é baixado no primeiro uso. Para trocar: `optimus config voz.modelo_stt small`. Com
placa NVIDIA, o reconhecimento usa a placa.

O Optimus ignora as frases que o Whisper costuma "inventar" no silêncio (como "Legendas pela comunidade
Amara.org").

## Palavra de ativação

Padrão: `optimus`. Troque com `optimus config voz.palavra_ativacao jarbas` (ou qualquer nome). O
reconhecimento aceita variações comuns de pronúncia.

## Problemas com microfone

- Linux: instale `libportaudio2` (o instalador já faz) e confira o microfone em Configurações > Som.
- Windows: Configurações > Privacidade > Microfone > permitir aplicativos da área de trabalho.
- Navegador: na primeira vez, permita o microfone no ícone de cadeado da barra de endereço. Fora do
  próprio PC, o navegador só libera o microfone em `localhost` ou HTTPS.


## Perfil pessoal Edton Braz

A entrada **Edton Braz** que já existia no catálogo era uma voz pública da ElevenLabs
(Mat(h)eus), não uma clonagem da voz pessoal do proprietário. Para criar o perfil pessoal,
abra **Estúdio > Vozes > Clonar uma voz**, mantenha o nome sugerido **Edton Braz**, escolha
uma gravação própria/autorizada e confirme a declaração de consentimento.

O pipeline aceita áudio ou vídeo, prepara a amostra em WAV mono a 24 kHz e exige de 5 a
90 segundos de fala. Prefira 10–30 segundos limpos, sem música, com voz natural. Ao salvar
o perfil com esse nome, ele substitui o item público de mesmo identificador. A conversa e
a fala do Optimus passam a usar a amostra pessoal via OmniVoice local quando o perfil
estiver disponível. Instale o extra opcional `omnivoice` para síntese; o modelo será
carregado sob demanda. Sem uma amostra pessoal salva, o comportamento anterior permanece.

Os vídeos de referência do proprietário não são baixados automaticamente pelo Optimus.
É necessário importar os arquivos MP4 ou áudio extraído dos vídeos. Não se declara
percentual de similaridade sem uma avaliação objetiva e auditiva.
