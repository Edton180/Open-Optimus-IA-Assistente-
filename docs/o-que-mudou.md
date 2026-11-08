# O que mudou em relação ao OpenJarvis

## O que é o OpenJarvis

O [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) é um framework de IA pessoal "local primeiro",
de pesquisadores de Stanford, lançado em 2026 sob a licença Apache 2.0. Ele traz motores locais
(Ollama, llama.cpp, MLX, vLLM), oito agentes (resumo matinal, pesquisa profunda, monitor contínuo,
ReAct, CodeAct...), um catálogo de "skills", medição de energia e custo, avaliações e um ciclo de
aprendizado com os próprios rastros de uso.

## Como as pessoas estão usando

Pesquisamos análises, tutoriais em vídeo, issues e projetos da comunidade:

- **Usos mais citados:** IA privada para documentos sensíveis, resumo matinal por voz (e-mail, agenda,
  notícias), pesquisa com citações, assistente de código e substituir APIs pagas em automações.
- **Pontos fortes:** tudo local por padrão, licença aberta, telemetria de energia.
- **Queixas:** projeto jovem e voltado a desenvolvedores; precisa de linha de comando e Python;
  recomenda 8 a 16 GB de VRAM e é lento em PCs sem placa; suporte ao Windows ainda irregular; sem
  controle do PC; voz limitada ao resumo matinal.
- **O que a comunidade pediu e construiu em volta:** palavra de ativação com modo conversa (issue #901),
  níveis de permissão com confirmação estrita, roteador rápido de comandos antes do modelo, fala
  interrompível frase por frase, filtro de "alucinações" do Whisper, painéis visuais estilo HUD,
  controle de teclado/mouse/janelas no Windows, lembretes por voz, memória de fatos e de documentos.

Fontes: [análise ComputerTech](https://computertech.co/openjarvis-review/),
[Toolhalla](https://toolhalla.ai/blog/openjarvis-ollama-local-first-personal-ai),
[issue #901](https://github.com/open-jarvis/OpenJarvis/issues/901),
[huburton/jarvis](https://github.com/huburton/jarvis),
[Shaan-alpha/jarvis-py](https://github.com/Shaan-alpha/jarvis-py),
[dmrr35/Open.Jarvis](https://github.com/dmrr35/Open.Jarvis), vídeos
["OpenJarvis + Ollama"](https://www.youtube.com/watch?v=0fdbQvwOrgQ) e
["Tu Agente de IA 100% gratis"](https://www.youtube.com/watch?v=SrR65-n5LIw).

## O que o Optimus faz diferente

| Tema | OpenJarvis | Optimus |
|---|---|---|
| Público | Desenvolvedores e pesquisa | Qualquer pessoa: instalador de um comando, interface visual em português |
| PCs fracos | Tabela de 2B a 27B; CPU lenta | Perfis de 0,8B a 35B, modelo MoE rápido na CPU, roteador rápido, modelo leve para voz, troca automática se a RAM acabar, prioridade baixa |
| Outros PCs e IAs | Motores de nuvem como alternativa | Lista de destinos com prioridade e troca automática; usa a placa de outro PC da casa |
| Voz | Resumo matinal falado | Palavra de ativação, modo conversa, confirmação por voz, 8 vozes masculinas e femininas (offline e online) já prontas |
| Controle do PC | Shell e arquivos no assistente de código | Arquivos, comandos, programas, processos, energia, teclado, mouse, tela, com níveis de risco |
| Casa | Não tem | Home Assistant, infravermelho, câmeras, Bluetooth, rede local |
| Segurança | Políticas e scanners para desenvolvedores | 4 níveis, 3 modos, confirmação estrita, bloqueio de comandos destrutivos, registro com segredos mascarados |
| Memória | Índices de documentos | Fatos, base de conhecimento que aprende com sites/arquivos e entra sozinha no prompt, lembretes |
| Interface | Web/desktop em inglês | Painel em português com histórico, projetos, personas, biblioteca de prompts, conversa em grupo, uso de CPU/RAM, funciona no celular |
| Sistemas | macOS, Linux, Windows (WSL2 recomendado) | Windows nativo, Linux e Android (Termux) |

## O que ficou de fora (por enquanto)

- Ciclo de aprendizado que re-treina o modelo (o OpenJarvis tem; exige GPU forte).
- Avaliações e medição de energia.
- Conectores de e-mail e agenda (planejados como plugins).
