# Casa inteligente

## Home Assistant integrado e gerenciado pelo Optimus

A tela **Casa inteligente** possui o painel **Home Assistant gerenciado pelo Optimus**. Use
**Instalar / configurar automaticamente** para detectar o sistema operacional, instalar/preparar o runtime
compatível, aguardar sua inicialização, provisionar o Home Assistant Container e validar a interface
por health-check HTTP. O painel também lista entidades reais e permite executar ações seguras nos
domínios compatíveis, sem depender de comandos Docker manuais.

- **Linux Debian/Ubuntu:** se o Docker Engine não existir, o Optimus solicita autorização administrativa
  pelo diálogo do sistema (pkexec), instala o pacote Docker e inicia o serviço.
- **Windows 10/11:** o Optimus instala Docker Desktop via winget e solicita sua inicialização. Dependendo
  do computador, o Windows pode exigir reinicialização, WSL2 e a conclusão inicial do Docker Desktop.
  Depois, clique novamente em instalar para provisionar o Home Assistant.
- **macOS:** o provisionamento do container pode ser usado com Docker Desktop já instalado e ativo.
  A instalação automática do Docker Desktop no macOS ainda não está habilitada.
- **Outros sistemas:** a interface informa que o provisionamento não foi validado e não simula instalação.

O Home Assistant fica em `http://127.0.0.1:8123` e seus dados ficam em
`<pasta de configuração do Optimus>/home_assistant`. O container reinicia automaticamente com o
Docker. O Optimus permite iniciar, parar, reiniciar, atualizar, criar backup e remover o container.
A remoção preserva os dados; a exclusão definitiva dos dados não é feita automaticamente.

**Importante sobre a edição instalada:** este provisionamento usa Home Assistant Container. Ele oferece
as integrações e entidades da plataforma Home Assistant, mas não inclui Supervisor, add-ons ou a loja
de add-ons do Home Assistant OS. Para rádio Zigbee/Matter/Bluetooth conectado por USB, o dispositivo
precisa estar acessível ao container e a compatibilidade depende do host. A primeira abertura ainda
exige criar a conta local e concluir o onboarding do Home Assistant; credenciais de serviços e
pareamento físico não podem ser inventados pelo Optimus.

Depois que o serviço estiver ativo, conclua o onboarding em sua interface e volte ao Optimus. Para
conectar um servidor já existente, informe sua URL e token na seção de conexão manual. O token é um
segredo: não o compartilhe. O Optimus mascara o token e pode reutilizar o valor já salvo ao testar
a conexão.

Documentação oficial: [instalação do Home Assistant](https://www.home-assistant.io/installation/) e
[autenticação e tokens](https://www.home-assistant.io/docs/authentication/#your-account-profile).

## O que funciona sem Home Assistant (limites atuais)

Sem Home Assistant, o controle direto nativo é limitado a aparelhos TP-Link Kasa compatíveis com o protocolo local antigo, Bluetooth suportado pelo sistema e câmeras/webcams cadastradas. Tuya/Smart Life, Tapo com KLAP, Intelbras, WAP, TVs e ar-condicionado de outras marcas **não são controlados diretamente pelo Optimus**: precisam de uma integração compatível no Home Assistant ou de um adaptador específico ainda não implementado.

O botão de procurar aparelhos Wi-Fi consulta a tabela de vizinhos que o sistema operacional já conhece (ARP/neighbor cache). Ele **não faz uma varredura ativa completa da sub-rede** e pode deixar de mostrar dispositivos que ainda não trocaram tráfego com o PC.

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

## Acesso fora de casa

O acesso pelo celular descrito no guia atual é para a rede local. Para controlar a casa fora do Wi-Fi, use uma VPN autenticada (por exemplo, WireGuard/Tailscale) ou uma solução remota HTTPS do Home Assistant. O Optimus ainda não fornece seu próprio relay remoto, pareamento de dispositivos ou túnel de ponta a ponta. **Não encaminhe a porta 8123 nem exponha RTSP diretamente à internet.**

## Descoberta e compatibilidade de câmeras

Atualmente é possível cadastrar manualmente uma URL HTTP de snapshot ou RTSP, usar câmeras expostas como entidades `camera.*` pelo Home Assistant e webcams USB. Ainda não há descoberta ONVIF/WS-Discovery automática, perfis prontos por fabricante (Intelbras/WAP/Tapo/genéricas) nem grade de streaming contínuo. Cada câmera exige endereço/stream e credenciais válidas; modelos e firmwares variam.

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


## Descoberta automática de câmeras ONVIF

Na ferramenta **Casa**, use `casa_descobrir_onvif` para enviar um Probe WS-Discovery à rede local
(UDP multicast IPv4, grupo `239.255.255.250:3702`). A busca é limitada a 10 segundos e até 128
respostas. Ela identifica os endereços HTTP(S) anunciados pela câmera, mas **não autentica, não
altera configurações e não inicia gravação**. O resultado é uma sugestão de cadastro: confirme que
o IP pertence a um equipamento seu e configure as credenciais no fluxo seguro da interface.

A descoberta depende de multicast permitido pela rede; VLANs, isolamento de clientes Wi-Fi,
firewalls e alguns roteadores podem bloquear WS-Discovery. A ausência de resultados não prova que
não existam câmeras na rede. O suporte a streaming contínuo, gravação, timeline e gestão de
credenciais ONVIF ainda é uma etapa separada.


## Registro unificado (fundação interna)

O pacote `optimus.smart_home.registry` fornece um inventário local versionado de dispositivos,
com integração, fabricante/modelo, cômodo, capacidades, disponibilidade e nível de confiança do
estado (`confirmed`, `estimated` ou `unavailable`). O arquivo é gravado atomicamente e não possui
campos para tokens ou senhas. Esta fundação ainda não substitui o cadastro pela interface nem
migra automaticamente as câmeras e entidades já existentes; isso será integrado nas próximas
etapas sem apagar a configuração atual.


## Painel de aparelhos e comandos

Com o Home Assistant autenticado, **Atualizar aparelhos** consulta `/api/states` e lista entidades
controláveis de luzes, tomadas, ventiladores, persianas/cortinas, climatização, fechaduras e
reprodutores de mídia. Os comandos enviados pelo Optimus são limitados a serviços conhecidos
(`turn_on`, `turn_off`, `toggle`, abrir/fechar, travar/destravar), sem aceitar nomes de serviço
arbitrários enviados pela interface. A senha/token não é incluída nas respostas nem nos logs.

Se a interface informar **API desta instalação desatualizada**, atualize o Optimus pelo atualizador
integrado e reinicie o processo do servidor. O código atual registra explicitamente a rota
`GET/POST /api/casa/gerenciado`; um processo antigo que ainda esteja rodando não recebe rotas novas
apenas porque os arquivos do repositório foram atualizados.
