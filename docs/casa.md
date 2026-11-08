# Casa inteligente

## Home Assistant (recomendado)

O [Home Assistant](https://www.home-assistant.io) é um sistema livre que fala com milhares de aparelhos:
lâmpadas e tomadas Wi-Fi (Tuya/Smart Life, Sonoff, Shelly, TP-Link), Bluetooth, Zigbee, Matter,
Chromecast, TVs (Samsung, LG), ar-condicionado, aspiradores, fechaduras, sensores e câmeras. Para
aparelhos com **controle remoto infravermelho** (TV antiga, ar-condicionado, ventilador), use um emissor
IR como o Broadlink RM integrado ao Home Assistant.

1. Instale o Home Assistant num PC, Raspberry Pi ou máquina virtual e adicione seus aparelhos nele.
2. No Home Assistant: seu perfil > **Segurança** > **Tokens de acesso de longa duração** > Criar token.
3. No Optimus: **Casa inteligente**, informe o endereço (`http://IP:8123`) e o token, e clique em
   **Salvar e conectar**.

Depois é só falar: *"apaga a luz da sala"*, *"liga o ar em 22 graus"*, *"fecha a cortina"*, *"pausa a
TV"*, *"manda o comando ligar para o controle da TV"*, *"tira uma foto da câmera do portão"*.

Fechaduras, alarmes, portões de garagem e sirenes são tratados como **ações críticas** e sempre pedem
confirmação.

## Sem Home Assistant

| Pedido | O que acontece |
|---|---|
| "procure aparelhos Bluetooth" | lista os aparelhos próximos e o sinal (precisa do extra `casa`: `pip install bleak`) |
| "quem está conectado no Wi-Fi?" | lista IPs e endereços MAC que o PC enxerga na rede |
| "tira uma foto de http://192.168.0.30/snapshot.jpg" | salva a imagem da câmera IP |
| "foto da câmera rtsp://usuario:senha@192.168.0.31/stream" | salva um quadro (precisa do `ffmpeg`) |

As fotos ficam na pasta `cameras` dentro da pasta do Optimus.
