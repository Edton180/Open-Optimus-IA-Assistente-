# Configuração

Arquivo: `~/.config/optimus/config.toml` (Linux), `%APPDATA%\Optimus\config.toml` (Windows). A variável
`OPTIMUS_HOME` troca a pasta inteira (instalação portátil). Quase tudo também muda pela interface.

```bash
optimus config                       # mostra tudo
optimus config agente.modo seguro    # altera um valor
```

| Seção | Chave | Padrão | O que faz |
|---|---|---|---|
| geral | nome | `Optimus` | Nome do assistente |
| geral | usuario | | Como ele te chama |
| geral | personalidade | texto padrão | Prompt de sistema |
| motor | backend | `ollama` | Veja [motor.md](motor.md) |
| motor | url | `http://127.0.0.1:11434` | Endereço do motor |
| motor | chave_api | | Para provedores na nuvem |
| motor | modelo / modelo_rapido | automático | Modelos usados |
| motor | contexto / threads | 0 (automático) | |
| motor | temperatura | 0.6 | Criatividade |
| motor | manter_carregado | `30m` | Tempo do modelo na memória |
| agente | modo | `equilibrado` | `seguro`, `equilibrado`, `autonomo` |
| agente | max_passos | 12 | Ferramentas por pedido |
| agente | pasta_trabalho | pasta do usuário | Base dos caminhos relativos |
| voz | voz | `feminina` | `feminina`, `masculina` ou id |
| voz | velocidade | 1.0 | |
| voz | palavra_ativacao | `optimus` | |
| voz | modelo_stt | automático | `tiny` a `large-v3-turbo` |
| voz | falar_respostas | true | No `optimus voz` |
| internet | max_resultados | 5 | Resultados por pesquisa |
| web | host / porta | `127.0.0.1` / 8765 | Interface |
| web | senha | | Obrigatória para `--rede` |
| recursos | uso | `equilibrado` | `economico`, `equilibrado`, `maximo` |
| recursos | ram_minima_gb | 1.5 | Troca para o modelo rápido abaixo disso |
| recursos | prioridade_baixa | true | |
| ferramentas | internet, arquivos, comandos, programas, teclado_mouse, lembretes, memoria, casa, plugins | tudo ligado menos teclado_mouse | Liga/desliga grupos |
| casa | url / token | | Home Assistant |
| destinos | (lista) | vazia | Outros PCs e IAs, veja [rede.md](rede.md) |

## Pastas

| Caminho | Conteúdo |
|---|---|
| `config.toml` | configurações |
| `optimus.db` | conversas, memória, conhecimento, lembretes, personas, prompts |
| `registros/acoes.jsonl` | ações executadas |
| `vozes/` | vozes offline |
| `plugins/` | suas ferramentas |
| `capturas/`, `cameras/` | prints e fotos |
