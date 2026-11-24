# Auditoria de cobertura — Prompt Mestre Open Optimus v4.0

**Base examinada:** branch `audit/house-voice-web-models-2026-11`, derivada da `main` após o PR #39.  
**Método:** inventário do repositório, leitura estática dos módulos, documentação e testes existentes. Não houve acesso ao computador, câmeras, rede doméstica, chaves, modelos instalados ou periféricos do proprietário.

## Legenda

- **Presente (código):** existe implementação identificável no repositório; não significa validação em hardware real.
- **Parcial:** existe uma parte do fluxo, mas não cobre o requisito completo.
- **Ausente:** não foi encontrada implementação correspondente no inventário examinado.
- **Exige ambiente real:** só pode ser validado com hardware, rede, conta, credencial ou serviço externo.

## Fase 0 — recursos de sistema, rede e casa

| Requisito v4.0 | Evidência no repositório | Estado |
|---|---|---|
| Inventário de Wi-Fi/Ethernet, IP, MAC, fabricante, hostname e serviços | `optimus/tools/lan.py` descobre dispositivos Kasa; `optimus/tools/casa.py` lê câmeras e vizinhos conhecidos; `optimus/engine/rede.py` roteia motores de IA, não é scanner de LAN | **Parcial** — não existe inventário geral ativo de sub-rede, OUI, mDNS/Nmap e portas |
| Controle direto multi-marca de lâmpadas/tomadas | `lan.py` implementa protocolo TP-Link Kasa legado; Home Assistant REST em `tools/casa.py` pode controlar entidades integradas | **Parcial** — Tuya, Yeelight, Shelly, Sonoff e Tasmota não têm drivers diretos próprios encontrados |
| Bluetooth | `bluetooth_procurar` e `bluetooth_conectar` em `tools/casa.py`, usando extra Bleak e ferramentas do sistema | **Parcial** — pareamento/conexão dependem do SO e não há validação em cada plataforma/perfil |
| IR e hubs Broadlink/Tuya | A API do Home Assistant pode acionar integrações IR; não foi encontrado driver próprio USB/serial ou Broadlink | **Parcial via Home Assistant; driver direto ausente** |
| Alexa | `alexa_anunciar` em `tools/casa.py` usa serviço `notify/alexa_media` do Home Assistant | **Parcial** — não é integração bidirecional completa nem webhook local independente |
| Controle de PCs remotos, WoL, SSH/RPC | Não foi encontrado `network_controller.py` ou módulo equivalente dedicado | **Ausente** |
| Desligamento/reinício remoto | Sem agente remoto autenticado dedicado | **Ausente** |

## Fase 1 — autoatualização e privacidade

| Requisito | Evidência | Estado |
|---|---|---|
| Verificar/baixar atualização Git ou release | `optimus/updater.py`, `autoatualizar.py`, `releases.py`, ferramentas de atualização e `startup.py` | **Presente no código** |
| Proteger dados locais e bloquear segredos antes de commit | `optimus/privacy_guard.py` | **Presente no código** |
| Testes de atualização e sanitização | Suíte de testes existente; conferir cobertura e casos de bypass antes de habilitar upload automático | **Parcial até revisão de cobertura e execução** |
| Push/PR automático | Fluxos de GitHub existem como ferramenta, com push separado e explícito | **Parcial; requer credencial e teste com repositório de teste** |

## Fase 2 — SKYNETchat / Modo Red / estúdio visual

| Requisito | Evidência | Estado |
|---|---|---|
| Modo Red e seletor Rápido/MAX dedicado | Não foi encontrado módulo/tema específico correspondente no HUD | **Ausente** |
| OSINT, scanner de sites, fact-checker, pentest e forense | Ferramentas gerais de internet, arquivos e código existem; não foi encontrada suíte `skynet_suite.py` | **Parcial; suíte dedicada ausente** |
| Geração local de imagem/vídeo e personagens | Não foi encontrado `estudio_visual.py` nem pipeline ComfyUI/Stable Diffusion/Wan/LTX | **Ausente** |

## Fase 3 — conhecimento local

| Requisito | Evidência | Estado |
|---|---|---|
| Base Markdown | `optimus/knowledge/` contém referências de programação, rede, primeiros socorros, conversões e documentação | **Presente, mas não enciclopédia universal** |
| Indexação FTS5 | `optimus/conhecimento.py` e `optimus/banco.py` | **Presente no código** |
| Aprender/crawlear web e gravar conhecimento com revisão | Não foi identificado crawler profundo e fluxo completo de aprovação/reindexação automática | **Parcial/ausente** |

## Fase 4 — câmeras / God's Eye

| Requisito | Evidência | Estado |
|---|---|---|
| Webcam USB, snapshot HTTP, RTSP/FFmpeg e entidades camera do Home Assistant | `optimus/webcam.py` e `tools/casa.py` | **Presente para captura de quadros** |
| Descoberta ONVIF/WS-Discovery automática | Sem módulo ONVIF dedicado no inventário | **Ausente** |
| Mosaico de vídeo contínuo, baixa latência, PTZ e reconexão | Interface atual consulta imagens JPEG periodicamente; não foi encontrado pipeline de mosaico/streaming contínuo e PTZ | **Ausente/parcial** |
| Perguntas multimodais sobre imagem das câmeras | Captura de imagem existe; pipeline de análise contínua de múltiplas câmeras não foi comprovado | **Parcial** |

## Fase 5 — 3D e gestos

| Requisito | Evidência | Estado |
|---|---|---|
| Geração e exportação de peças STL/OBJ/GLB | Não foi encontrado `modelagem3d.py` ou motor CAD equivalente | **Ausente** |
| Hand tracking MediaPipe para montar/desmontar peças | `gestos.js` existe, mas não foi encontrada integração 3D/MediaPipe com seleção de peças | **Parcial; requisito 3D ausente** |
| Holograma Three.js | Não foi encontrado `hologram.js` ou renderizador de modelos 3D | **Ausente** |

## Fase 6 — Optimus Code

| Requisito | Evidência | Estado |
|---|---|---|
| Ferramentas de código | `optimus/tools/codigo.py` e `tools/arquivos.py` | **Parcial** |
| Agente autônomo multi-arquivo com diff, execução de testes, autocorreção e PR | Não foi encontrado `optimus_code.py` nem loop de engenharia completo equivalente | **Ausente como agente completo** |

## Fase 7 — documentos e skills

| Requisito | Evidência | Estado |
|---|---|---|
| Operações PDF | `tools/pdf.py` e `tools/pdf_suite.py` | **Presente em expansão; CI não prova paridade integral com iLovePDF** |
| Leitura/edição de arquivos gerais | `tools/arquivos.py`, biblioteca e estúdio | **Parcial** |
| Suite unificada DOCX/XLSX/PPTX/CSV/MD | Dependências e alguns fluxos existem; não foi encontrada uma fachada `documentos.py` cobrindo toda a matriz | **Parcial** |
| Computer Use, Deep Research, Data Analyst, Smart Home Maestro e Media Summarizer como skills nativas | Sem diretório `skills_nativas/` encontrado | **Ausente como pacote integrado** |

## Fase 8 — telas, cluster e motores

| Requisito | Evidência | Estado |
|---|---|---|
| Multi-telas sincronizadas por WebSocket | Não foi encontrado módulo `multitela.js` nem rotas dedicadas | **Ausente** |
| Cluster de GPU/CPU entre PCs | `engine/rede.py` encaminha requisições a motores remotos configurados; não agrega recursos de hardware em cluster | **Parcial** |
| Detectar upgrade de hardware e comparar snapshot persistente | `hardware.py` detecta o hardware atual e recomenda perfis; não foi comprovado fingerprint persistido com eventos de upgrade | **Parcial** |
| Ollama e APIs OpenAI-compatible | `engine/ollama.py`, `engine/openai_compat.py`, `engine/rede.py` | **Presente para backends listados; não significa compatibilidade universal** |
| llama.cpp, LM Studio, vLLM | Endpoints compatíveis OpenAI listados em `engine/rede.py` | **Parcial; validar por backend/modelo** |
| MLX, KoboldCpp, GPT4All e fallback universal | Não foram encontrados adaptadores dedicados no inventário | **Ausente/parcial** |
| Windows/Linux/macOS/Termux autostart | `startup.py` contempla systemd, Agendador de Tarefas, launchd e Termux:Boot | **Presente no código; validar instalação em cada SO** |

## Fase 9 — licença

Arquivos de licença e metadados de pacote existem. A conformidade jurídica da licença dupla deve ser revisada separadamente; presença de arquivos não é parecer jurídico.

## Complementos — persistência, memória e hardware

| Requisito | Evidência | Estado |
|---|---|---|
| Serviço 24/7 com recuperação | `startup.py` instala serviço/tarefa com reinício em falha; não foi encontrado daemon supervisor próprio | **Parcial** |
| Retomada de sessões, câmeras e tarefas após reboot | Persistência de conversa/memória existe; retomada completa de estado e streams não foi comprovada | **Parcial/ausente** |
| Hotkey global e wake word sempre ativo | Voz ao vivo e wake phrase existem no fluxo da interface; hotkey global e wake word independente do navegador não foram comprovados | **Parcial** |
| Córtex episódico/semântico | `tools/memoria.py` e `banco.py` oferecem memória persistente; não foi encontrado `cortex.py` | **Parcial** |
| Fingerprint e notificação de upgrade | Detecção atual de hardware existe; comparação de snapshots e notificação proativa não foi comprovada | **Parcial** |

## Próximas entregas em ordem

1. **P0 — Confiabilidade:** CI verde em todos os quatro ambientes, diagnóstico único de dependências/integrações, smoke tests reais opcionais para Ollama, TTS e pesquisa.
2. **P1 — Rede e casa:** scanner LAN limitado à rede privada local, ONVIF/WS-Discovery, matriz de câmeras e adaptadores documentados; Home Assistant como ponte multi-marca e autenticação remota via VPN/TLS.
3. **P1 — Pesquisa:** reforçar correspondência de entidades, ler fontes relevantes, registrar data/provedor, deduplicar e distinguir evidência primária de notícia/opinião.
4. **P2 — Voz:** importar amostra autorizada, testar motores com áudio não vazio e comparar pronúncia/latência; não rotular preset público como clone.
5. **P2 — Módulos ausentes:** 3D/gestos, telas distribuídas, agente de código, skills e daemon/córtex em PRs separados, cada um com critérios de aceite e testes próprios.

## Limites de validação

A CI automatizada pode provar regressões de código em Ubuntu/Windows e versões de Python. Não prova que uma câmera Intelbras/WAP, lâmpada Tuya, ar-condicionado, Echo, GPU, microfone ou alto-falante específico funcione. Esses itens exigem integração com os equipamentos e credenciais do proprietário. Nenhum scanner deve tentar acessar redes de terceiros; o inventário ativo deve limitar-se à LAN privada autorizada.
