# Voz

## Conversar por voz

**Terminal:** `optimus voz`. Diga **"Optimus, ..."** e o pedido. Depois da resposta, por 25 segundos você
pode continuar falando sem repetir o nome (modo conversa). "Pode parar" ou "tchau" encerram o modo
conversa. Ctrl+C sai.

**Interface:** segure o botão 🎙️, fale e solte. O botão 🔈/🔊 liga a leitura das respostas. Funciona
também no celular conectado ao PC.

Ações que precisam de confirmação são perguntadas em voz alta. Responda "sim" (ou "pode") nas moderadas
e **"confirmo"** nas críticas. Qualquer "não", "espera" ou "cancela" nega, mesmo junto de um "sim".

## Vozes prontas

| Voz | Gênero | Tipo | Precisa de |
|---|---|---|---|
| Dora | feminina | natural, offline | arquivos de voz (o instalador baixa) |
| Alex | masculina | natural, offline | idem |
| Santa | masculina, grave | natural, offline | idem |
| Francisca | feminina | neural, online | internet |
| Thalita | feminina | neural multilíngue, online | internet |
| Antonio | masculina | neural, online | internet |
| Sistema (feminina/masculina) | ambos | voz do Windows (Maria, Daniel), espeak-ng no Linux, voz do Android | nada |

Escolha em **Configurações > Voz** (botão ▶ Ouvir para testar) ou:

```bash
optimus vozes                      # lista e mostra quais estão prontas
optimus config voz.voz masculina   # melhor voz masculina disponível
optimus config voz.voz feminina
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
