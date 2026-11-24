# Paridade funcional com Meta Muse Gadget SDK

Este documento compara as capacidades do **agente Linux** e dos SDKs de dispositivos do
repositório oficial `facebookincubator/muse-gadget-sdk` com o Open Optimus. O SDK da Meta
constrói gadgets que se conectam ao aplicativo/serviço Muse; ele não é, por si só, um LLM
autônomo. O objetivo aqui é oferecer no Optimus capacidades equivalentes para operar o
computador e dispositivos locais, sem exigir integração com a conta ou a nuvem Muse.

Fonte de referência: README do Linux SDK, instruções `linux/AGENTS.md`, protocolo
`protocols/DEVICE.md` e README principal do repositório oficial.

## Linux agent: equivalência

| Capacidade Muse Linux | Equivalente no Optimus | Estado real / diferença |
|---|---|---|
| `system.run` — executar comandos e retornar saída/código | `executar_comando` | Existe em Windows/Linux/macOS/Android. É síncrono, timeout configurável até 600 s e limitado a 12.000 caracteres de stdout e 4.000 de stderr. Não há ainda o mesmo protocolo remoto de sessão. |
| `file.read` — leitura em blocos de 64 KB | `ler_arquivo` | Existe, mas limita a 2 MB e 20.000 caracteres; não oferece leitura paginada por offset de 64 KB. |
| `file.write` — escrita em blocos e substituição somente ao concluir | `escrever_arquivo` | Existe, mas grava o conteúdo recebido de uma vez; não tem protocolo de chunks nem troca atômica após concluir. |
| `device.health` — uptime, carga, memória, disco e temperatura | `info_sistema` / `desempenho` | CPU, RAM, disco, bateria e uptime estão disponíveis; temperatura e carga detalhada não são uniformes em todos os sistemas. |
| Até quatro comandos simultâneos | Ciclo de ferramentas do agente | Não há garantia de limite global de quatro comandos nem política equivalente para comandos órfãos após desconexão. |
| Comandos customizados | Plugins Python e servidores MCP | Extensibilidade existe; contratos, descoberta e limites de execução são diferentes. |
| Pareamento e sessão criptografada Noise | Interface web local com senha / MCP | Não equivale ao pareamento BLE, credenciais de dispositivo e transporte Noise do Muse. |
| Reconexão e ciclo de vida de sessão | Servidor web local | Não há equivalência integral ao protocolo persistente de dispositivo Muse. |

## Recursos de voz e vídeo do SDK

O Linux SDK documenta chamadas de voz em WAV e ao vivo, chamadas de vídeo com mídia H.264/Opus,
wake word opcional, interrupção (barge-in), controle de turnos e limites de buffers/filas.

O Optimus possui reconhecimento e síntese de voz, conversa ao vivo no navegador, câmeras e
ferramentas de áudio/vídeo no estúdio. Isso **não prova** paridade com o transporte de chamadas
de voz/vídeo do Muse: não foi identificada uma implementação equivalente de Noise + SRTP,
controle de chamadas por VM, codec e ciclo de vida de chamada.

## ESP32 Device SDK

O SDK ESP32 permite criar firmware de gadgets com:
- telas e interfaces de botões/toque;
- entrada e saída de áudio;
- sensores e atuadores;
- conectividade Wi-Fi/Bluetooth e descoberta/controle BLE;
- comandos anunciados por `link.register` e executados por `link.invoke`;
- câmera e streaming de vídeo para placas compatíveis;
- apps WebAssembly opcionais em placas suportadas;
- descrição do dispositivo via `device.guide` e capacidades estruturadas.

O Optimus controla parte de dispositivos locais por Home Assistant, TP-Link Kasa, Bluetooth,
câmeras e rede local, mas não contém atualmente um SDK/firmware ESP32 equivalente, nem implementa
os protocolos Muse de registro, pareamento e invocação. Para alcançar a mesma classe de uso, o
Optimus precisa de uma camada própria de dispositivos/gadgets e adaptadores por hardware.

## Plano de implementação

### P0 — equivalência básica do agente Linux
1. Leitura paginada de arquivos por offset/tamanho, com limite por bloco.
2. Escrita em chunks para arquivo temporário, validação de tamanho/hash e substituição atômica
   somente ao concluir; limpeza segura de uploads incompletos.
3. Health report padronizado: uptime, load average quando disponível, CPU, RAM, disco,
   temperatura e bateria, com campos ausentes explicitamente nulos.
4. Executor de comandos com limite global de concorrência, cancelamento, timeout, captura
   limitada de saída e auditoria de início/fim/exit code.
5. Testes em Linux, Windows e macOS para os recursos que cada sistema suporta.

### P1 — dispositivos e sessões remotas seguras
1. Registro de dispositivos com identidade estável, nome, versão, capacidades e guia.
2. Contrato de comandos tipados com validação de parâmetros, timeout e resultados padronizados.
3. Sessões autenticadas, criptografadas, revogáveis e com pareamento explícito; sem abrir
   controle remoto por padrão.
4. Comandos customizados via plugins/MCP com limites, permissões e trilha de auditoria.
5. Reconexão e cancelamento previsíveis; comandos de sessão antiga não podem ser repetidos
   silenciosamente.

### P2 — multimodal e hardware
1. Camada de áudio full/half duplex com interrupção e cancelamento de resposta.
2. Pipeline de vídeo em tempo real com limites de buffer, descarte de frames e testes de codec.
3. Adaptadores ESP32/serial/BLE/MQTT/Home Assistant para sensores, telas e atuadores.
4. Guia/capabilities por dispositivo e descoberta em runtime.
5. Runtime de apps embarcados apenas quando o hardware suportar e com sandbox explícito.

## Critério de conclusão

Uma linha só pode mudar para **Implementado e validado** depois de:
- código funcional integrado;
- testes unitários e de integração;
- testes E2E nos sistemas operacionais suportados;
- documentação de dependências e permissões;
- tratamento de falhas, timeouts, desconexão e recuperação;
- CI verde em todas as combinações aplicáveis.

Não copiar código ou credenciais da Meta. Reimplementar os contratos necessários de forma independente,
respeitando a licença Apache-2.0 e as licenças de terceiros do SDK de referência.
