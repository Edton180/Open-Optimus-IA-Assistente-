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
| "procure tomadas Kasa" | acha tomadas, interruptores e lâmpadas **TP-Link Kasa** na Wi-Fi (veja abaixo) |
| "liga a tomada da sala" / "brilho da lâmpada em 40" | **controla** o aparelho Kasa pelo IP, sem nuvem |
| "procure aparelhos Bluetooth" | lista os aparelhos próximos e o sinal (precisa do extra `casa`: `pip install bleak`) |
| "conecte o fone AA:BB:CC:DD:EE:FF" | pareia e conecta (Linux: `bluetoothctl`; Mac: `brew install blueutil`; Windows: abre a tela de Bluetooth) |
| "quem está conectado no Wi-Fi?" | lista IPs e endereços MAC que o PC enxerga na rede |
| "tira uma foto de http://192.168.0.30/snapshot.jpg" | salva a imagem da câmera IP |
| "foto da câmera rtsp://usuario:senha@192.168.0.31/stream" | salva um quadro (precisa do `ffmpeg`) |
| "tira uma foto pela webcam" | foto da webcam por cabo ou do notebook (sempre pede confirmação) |

As fotos ficam na pasta `cameras` dentro da pasta do Optimus.

## Tomadas e lâmpadas TP-Link Kasa (sem Home Assistant)

O Optimus fala direto com aparelhos **TP-Link Kasa** (tomadas HS100/HS103/HS110/KP105/KP115,
interruptores HS200/HS220, lâmpadas KL110/KL130...) pela sua própria rede Wi-Fi: sem nuvem, sem conta
e sem Home Assistant. Ele usa o protocolo local da TP-Link (porta 9999).

1. Configure o aparelho uma vez pelo app **Kasa** da TP-Link, na mesma Wi-Fi do PC.
2. Peça *"procure tomadas Kasa"*: aparecem nome, modelo, se está ligado e o IP.
3. Peça *"liga a tomada 192.168.0.42"*, *"desliga a lâmpada da sala"*, *"alterna a tomada"* ou
   *"brilho da lâmpada em 40"*. Como as luzes do Home Assistant, isso é feito na hora; no modo
   `seguro` (`optimus config agente.modo seguro`) ele pede confirmação antes.

Dica: fixe o IP do aparelho no roteador (reserva de DHCP) para ele não mudar.

Limites: aparelhos **Tapo** e Kasa com firmware novo (protocolo KLAP, criptografado) não respondem a esse
protocolo antigo; para eles use o Home Assistant. Outras marcas (Tuya/Smart Life, Wiz, Yeelight, Shelly)
também pelo Home Assistant, por enquanto.

## Webcams por cabo (USB) e a câmera do notebook

Toda webcam ligada no PC vira uma câmera do Optimus, com id `usb:0`, `usb:1`... Ela aparece na tela
**Casa** com imagem ao vivo e pode ser usada em *"tira uma foto pela webcam"* ou *"foto da câmera usb:1"*.
Funciona no Windows, Linux e macOS.

- Para ler a imagem o Optimus usa o **OpenCV** se estiver instalado (`pip install opencv-python`) ou o
  **ffmpeg** (o instalador já coloca no Linux e no Mac; no Windows: `winget install Gyan.FFmpeg`).
- A foto pela webcam **sempre pede confirmação**, em qualquer modo, porque a câmera pode estar apontada
  para você (e assim um texto escondido numa página nunca tira fotos sozinho).
- As imagens ficam só no seu PC, na pasta `cameras` do Optimus.
- Para esconder as webcams: `optimus config casa.webcams false`.
- No Mac, na primeira vez, o macOS pede permissão de câmera para o Terminal (ou o app que abriu o
  Optimus): Ajustes do Sistema > Privacidade e Segurança > Câmera.

Também dá para cadastrar uma webcam com nome em `config.toml`:

```toml
[[cameras]]
nome = "Câmera da garagem"
url = "usb:1"
```

## Gestos pela câmera

Na interface, aperte **✋ Gestos** no topo. Use a webcam do notebook ou uma por cabo (clique na
imagem pequena no canto para trocar de câmera).

| Gesto | O que faz |
|---|---|
| ✋ mão aberta | para a fala e cancela o pedido em andamento |
| 👍 polegar para cima | aprova a confirmação aberta |
| 👎 polegar para baixo | nega a confirmação aberta |
| ✌️ dois dedos (paz) | liga/desliga a conversa ao vivo |
| ☝️ indicador para cima | faz um pedido falado (como o botão do microfone) |

- Segure o gesto por meio segundo. Ele vale uma vez; para repetir, abaixe a mão e faça de novo.
- **Ações críticas nunca são aprovadas só com gesto**: use o botão ou diga "confirmo".
- O reconhecimento roda **no navegador** (MediaPipe, do Google). O vídeo não sai do PC; na primeira vez o
  navegador baixa a biblioteca e o modelo (cerca de 18 MB), então precisa de internet nesse momento.
- A imagem pequena no canto fica visível enquanto os gestos estão ligados, para você sempre saber que a
  câmera está em uso. Aperte o botão de novo para desligar e soltar a câmera.
