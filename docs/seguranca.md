# Segurança

O Optimus não filtra o que você conversa: isso depende do modelo e do prompt que você escolher. O que ele
protege são as **ações no seu computador e na sua casa**, porque um modelo de IA pode errar.

## Níveis de risco

| Nível | Exemplos | O que acontece |
|---|---|---|
| Livre | ler e listar arquivos, pesquisar, hora, `ls`, `git status`, ver processos | executa |
| Moderado | criar arquivo novo, abrir programa, digitar, comando desconhecido, ligar luz | executa (no modo seguro, pergunta) |
| Crítico | apagar, sobrescrever, mover, encerrar processo, desligar, reiniciar, `sudo`, instalar pacotes, `curl ... \| sh`, mexer no registro, `git push`, destrancar fechadura | **sempre pergunta**, em qualquer modo |
| Bloqueado | `rm -rf /`, formatar disco, `mkfs`, `dd` para o disco, `diskpart`, fork bomb, PowerShell codificado (`-enc`), apagar `C:\Windows`, apagar a pasta pessoal inteira | **nunca executa**; se quiser, faça você mesmo |

Escrever, mover ou apagar dentro das pastas do sistema (`/etc`, `/usr`, `C:\Windows`, `C:\Program Files`...)
também é crítico ou bloqueado.

## Confirmação

- Na interface: cartão amarelo (moderado) ou vermelho (crítico) com **Aprovar** e **Negar**.
- No terminal: digite `sim` (moderado) ou `confirmo` (crítico).
- Por voz: "sim" ou "pode" para moderado, **"confirmo"** para crítico.

A leitura é estrita: qualquer negação vence ("sim, mas não agora" é **não**), e só um sim claro aprova.
Se você negar, o Optimus é instruído a não tentar de novo e perguntar o que você prefere.

## Registro

Tudo que é executado vai para `registros/acoes.jsonl` e para a tela **Ações e segurança**: quando, qual
ferramenta, argumentos, nível e decisão (automática, aprovada, negada, bloqueada). Senhas, tokens e chaves
aparecem como `[oculto]`.

## Acesso pela rede

A interface só escuta no próprio PC (`127.0.0.1`). Para abrir para o celular (`optimus gui --rede`), o
Optimus exige uma senha (`optimus config web.senha ...`). Use só em redes de confiança.

## Boas práticas

- Comece no modo **equilibrado** ou **seguro**.
- Deixe `teclado_mouse` desligado se não precisar.
- Use uma pasta de trabalho (`agente.pasta_trabalho`) para limitar onde os caminhos relativos caem.
- Leia o comando no cartão de confirmação antes de aprovar.
