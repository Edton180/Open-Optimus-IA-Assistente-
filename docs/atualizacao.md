# Autoatualização pelo GitHub (sem perder dados, sem vazar nada)

O Optimus pode se atualizar a partir do repositório oficial e, quando você quiser, enviar de
volta as melhorias que ele mesmo fez no código. Tudo passa por uma **barreira de privacidade**
que impede o vazamento de qualquer dado pessoal seu.

## Onde ficam os seus dados

Suas memórias, lembretes, histórico de conversas, chaves de API, `config.toml` e modelos
baixados ficam em `OPTIMUS_HOME` (por padrão `~/.config/optimus` no Linux, `%APPDATA%\Optimus`
no Windows) — **fora** da pasta do Git. Por isso, baixar uma atualização (`git pull`) nunca
toca nesses arquivos: eles são sempre preservados.

## Baixar atualizações

- **Painel/voz:** botão "🔄 Verificar/Baixar Atualizações", ou diga *"Optimus, veja se tem
  atualização"*.
- **Ferramentas:** `atualizacao_verificar` (só olha, não muda nada) e `atualizacao_baixar`
  (aplica com `git pull --ff-only`).

`atualizacao_baixar` só avança se a árvore de trabalho estiver limpa. Se houver mudanças
locais não salvas, ele para e avisa, para não sobrescrever nada.

## A barreira de privacidade (Zero-Leak)

O módulo `optimus/privacy_guard.py` é a regra crítica: **antes de qualquer commit automático**
feito pelo Optimus, ele varre o que seria enviado e:

1. **Bloqueia arquivos inteiros** que nunca podem subir — bancos (`*.db`, `*.sqlite`),
   segredos (`.env`, `*.pem`, `*.key`), o `config.toml` com chaves reais, memórias,
   históricos, gravações de câmera e backups.
2. **Mascara segredos** dentro do código antes do commit, trocando por marcadores genéricos:

   | O que ele acha | Vira |
   | --- | --- |
   | Chaves de API (OpenAI, Anthropic, GitHub, Google, Groq, Slack, AWS) | `<SUA_API_KEY>`, `<SEU_GITHUB_TOKEN>`, ... |
   | Chaves privadas (`-----BEGIN PRIVATE KEY-----`) | `<CHAVE_PRIVADA>` |
   | `senha`/`password`/`token` = ... | `<SUA_SENHA>` / `<SEU_TOKEN>` |
   | Senha de Wi-Fi (`wpa_psk`) | `<SUA_SENHA_WIFI>` |
   | IP da sua casa/rede | `<SEU_IP>` |
   | Endereço MAC | `<SEU_MAC>` |
   | Caminhos com seu nome (`C:\Users\voce`, `/home/voce`) | `.../<USUARIO>` |

Se a revisão encontrar um arquivo proibido ou um segredo, o commit é **recusado** e o
`staging` do Git é desfeito. Nada sensível fica pronto para enviar por engano.

IPs seguros de código (`127.0.0.1`, `0.0.0.0`, `8.8.8.8`), MACs genéricos e placeholders já
existentes não são mascarados, para não sujar o código à toa.

## Enviar melhorias ao GitHub

O envio (`git push`) é sempre **manual e explícito** — nunca roda sozinho junto com um commit.
Ele também revisa o que será enviado pela barreira de privacidade uma última vez e recusa se
achar qualquer coisa sensível.

## Configuração

No `config.toml`:

```toml
[atualizacao]
# Pasta do repositório (vazio = a pasta onde o Optimus está instalado, se for um clone do Git).
repo = ""
# Verificar atualizações automaticamente ao iniciar.
ao_iniciar = false
```
