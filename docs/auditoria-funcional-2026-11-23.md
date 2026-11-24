# Auditoria funcional do Open Optimus — 23/11/2026

## Escopo e método

Auditoria estática do código, documentação, testes e fluxos expostos na interface da branch `main` após o merge do PR #39. Não foi possível executar o aplicativo em um PC/Android real nem conectar esta sessão à rede, câmeras, lâmpadas, ar-condicionado, Ollama ou credenciais do proprietário. Por isso, os itens abaixo distinguem implementação presente de validação física.

## Resultado executivo

O repositório tem uma base funcional extensa, mas **não é correto afirmar que todos os recursos anunciados estão integralmente implementados ou validados**. Existem integrações reais, recursos parciais e promessas que excedem o código atual.

## Matriz de evidências

| Área | O que existe no código | Estado comprovável | Lacuna / próximo teste |
|---|---|---|---|
| Pesquisa na internet | DuckDuckGo (biblioteca e HTML), Bing, Wikipédia seletiva; deduplicação, pontuação lexical e expansão pontual de sigla | Parcial; testes unitários simulam provedores e filtros | Não há verificação factual independente, score semântico robusto, extração sistemática de datas/autoridade nem leitura automática de cada fonte para confirmar alegações. Não garante precisão em toda pergunta. |
| Leitura de páginas | GET HTTP, título e extração de texto | Parcial | Faltam testes E2E em sites reais, tratamento específico de paywall/JS/PDF e políticas completas contra SSRF/redes internas. |
| Modelos IA | Catálogo JSON, recomendação por hardware, ferramentas de pull e verificação de presença no Ollama | Implementação presente; testes usam Ollama falso | CI não prova download real, checksum, espaço em disco, retomada, instalação do Ollama por sistema nem inferência real após download. Backends llama.cpp/LM Studio/API não usam o mesmo fluxo de instalação de modelos. |
| Voz em tempo real | Reconhecimento navegador/Whisper, TTS por motores e fallback | Parcial; testes de componentes e roteamento | Precisa de matriz física de microfones/alto-falantes, Android/Termux, cancelamento, latência e permissões por navegador/SO. |
| Estúdio de voz | Narrar, clonar com consentimento, transcrever, legendar, traduzir, dublar, audiolivro e filas | Código e testes unitários presentes | Não foi validada qualidade de saída com modelos reais nem aceleração GPU em cada plataforma. OmniVoice/Chatterbox/Demucs são extras pesados separados. |
| Voz “Edton Braz” | ID fixo de voz pública ElevenLabs rotulada “Matheus - Friendly and Energetic”; fallback Titan/Prime | Preset cadastrado, não clone pessoal validado | Não há amostra de referência acessível nesta auditoria. Não é possível afirmar semelhança com a voz do usuário. Importar amostra consentida e comparar audições é obrigatório. |
| Casa inteligente | Home Assistant REST, Assist, Kasa local antigo, Bluetooth, rede ARP, webcam USB, câmera HTTP/RTSP e entidades camera do HA | Adaptadores reais presentes, mas testes automatizados de casa eram ausentes antes desta auditoria | Sem Home Assistant, o controle nativo direto é principalmente Kasa compatível. Tuya, Tapo KLAP, Intelbras, WAP, TV e ar-condicionado não têm adaptadores nativos universais. |
| Descoberta Wi-Fi | Consulta `ip neigh` / `arp -a` | Só cache de vizinhos | Não é varredura ativa de sub-rede; dispositivos silenciosos podem não aparecer. Não equivale a inventário completo. |
| Câmeras | Webcam USB, URL de snapshot HTTP, RTSP via FFmpeg, câmera Home Assistant | Prévia JPEG consultada a cada ~1,2 s na interface | Não é vídeo contínuo, NVR, ONVIF/WS-Discovery, descoberta automática de marcas nem mosaico de streams de baixa latência. Credenciais e perfis variam por modelo/firmware. |
| Acesso remoto | Interface móvel local com senha | Acesso remoto universal não comprovado | Fora da rede local requer VPN ou serviço remoto HTTPS configurado. Não existe relay remoto próprio/pareamento seguro de dispositivos implementado. Não expor portas de câmera/HA diretamente. |
| Muse Gadget SDK | Documento de comparação e parte das funções de agente local | Paridade parcial documentada | Sessões pareadas Noise, chunks retomáveis, streaming multimodal equivalente, SDK/firmware ESP32 e protocolo de gadgets continuam pendentes. |
| PDF | Suíte expandida no PR #39 | CI do PR passou em Ubuntu/Windows, Python 3.10/3.12 | Isso valida testes automatizados, não paridade completa com iLovePDF nem todos os documentos reais. |

## Achados específicos que motivaram alterações nesta branch

1. A tela Casa apresentava a descoberta Wi-Fi como se fosse uma busca geral, mas o código consulta apenas o cache ARP/neighbor do sistema.
2. A documentação chamava as câmeras de “ao vivo”, mas a interface faz requisições de imagem JPEG em intervalo aproximado de 1,2 s. Isso é uma prévia periódica, não streaming contínuo.
3. A documentação dava a entender que marcas variadas funcionavam sem Home Assistant. O código direto nativo tem suporte limitado à geração antiga do protocolo TP-Link Kasa; outras marcas dependem de Home Assistant/adaptador.
4. A opção “Edton Braz” usa um ID de voz pública ElevenLabs (“Matheus”). Isso não prova clonagem ou semelhança com a voz pessoal do proprietário. Sem chave, usa fallback.
5. Antes desta branch, não havia arquivo dedicado de testes para a integração Home Assistant/casa. Foi adicionado diagnóstico somente de leitura e testes com API simulada.

## Alterações nesta branch

- Ferramenta `casa_diagnostico`: testa conexão real com Home Assistant, lista entidades/domínios/câmeras e identifica webcams locais, sem enviar comandos.
- Testes unitários para conexão, falha, entidades e garantia de que o diagnóstico não faz POST.
- README e guias ajustados para não prometer descoberta total, streaming contínuo ou compatibilidade nativa universal.
- Voz Edton Braz descrita corretamente como preset público até que uma amostra de referência seja fornecida e comparada.

## Plano de correção prioritário

### P0 — confiabilidade e transparência
- Cobertura de testes da API Home Assistant: serviço por domínio, erros HTTP, timeout, estados e atributos climate/light/fan/media_player.
- Pesquisa: validar URLs, rejeitar páginas fora do tópico, separar fontes primárias/secundárias, registrar datas e exigir leitura de fonte para fatos atuais.
- Modelos: teste de integração opcional com Ollama real, checagem de disco, download interrompido, lista final e inferência de smoke test.
- Estúdio: smoke tests de cada motor, teste de geração de áudio não vazio, reprodução e exportação, com extras presentes/ausentes.
- Diagnóstico único que mostre dependências, serviços, permissões, armazenamento, dispositivos e recursos indisponíveis.

### P1 — casa inteligente interoperável
- Descoberta ONVIF/WS-Discovery com credenciais inseridas pelo usuário e sem tentativa de quebrar autenticação.
- Adaptadores por protocolo: Home Assistant, ONVIF/RTSP, MQTT, Matter, Tuya local/cloud autorizado, Kasa KLAP/Tapo e integrações oficiais dos fabricantes.
- Inventário de rede ativo, limitado à sub-rede local, com timeout, consentimento explícito e distinção entre “detectado”, “identificado” e “controlável”.
- Grade multi-câmera com streams WebRTC/HLS/MJPEG suportados, controles de qualidade, reconexão, autenticação e indicador visível de gravação/captura.
- Acesso remoto via VPN/relay autenticado, tokens revogáveis, TLS, autorização por dispositivo e logs; nunca abrir acesso público por padrão.

### P2 — voz pessoal e experiência
- Receber a amostra original de voz do proprietário, medir duração/ruído/idioma e fazer clonagem somente com consentimento.
- Comparar a voz gerada com a amostra por audição humana; não prometer “muito parecida” com base apenas em nome de preset.
- Testes de latência, pronúncia pt-BR, prosódia, emoção, diarização e dublagem com exemplos reais autorizados.
- Fallback deve informar claramente quando muda de motor/voz e não apresentar o fallback como a voz original.

## Critério de aceite

Uma capacidade só pode ser marcada como **funcional e validada** quando houver: implementação, teste unitário, teste de integração com dependência real ou simulador fiel, teste E2E nas plataformas anunciadas, tratamento de falhas e documentação do que exige hardware/conta/credencial. Testes simulados não são evidência de funcionamento físico.
