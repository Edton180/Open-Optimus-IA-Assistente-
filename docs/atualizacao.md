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

- **Terminal:**

  ```bash
  optimus atualizar --verificar   # só olha e mostra o que mudou
  optimus atualizar               # pergunta e atualiza
  optimus atualizar --sim         # atualiza sem perguntar
  optimus atualizar --voltar      # desfaz a última atualização
  optimus atualizar --canal beta  # olha também os pré-lançamentos
  ```

- **Painel/voz:** diga *"Optimus, veja se tem atualização"*, *"atualiza"* ou *"volta a
  versão anterior"*.
- **Ferramentas:** `atualizacao_verificar` (só olha), `atualizacao_baixar` e
  `atualizacao_voltar` (essas duas sempre pedem confirmação).

O Optimus escolhe sozinho o jeito certo de atualizar:

| Como foi instalado | Como atualiza | Como volta |
| --- | --- | --- |
| Clone do Git | `git pull --ff-only`. Só avança se não houver mudanças locais não salvas. | `git reset --keep` para o commit de antes (recusa se fosse apagar algo seu). |
| pip, ZIP ou instalador (sem Git) | Baixa a **release** do GitHub, confere o **SHA-256** publicado no `SHA256SUMS` e só então troca a pasta `optimus/`. | Restaura a cópia da versão anterior guardada em `OPTIMUS_HOME/backups`. |

Se o download não bater com a soma SHA-256, se a release não publicou as somas ou se o pacote
tiver um caminho suspeito, **nada é alterado**.

## Atualização automática

Com `ao_iniciar = true`, o Optimus verifica ao abrir e mostra um aviso no painel. Ele só
instala **sozinho** quando todas estas condições valem:

1. foi instalado sem Git (num clone ele apenas avisa);
2. `automatico = true`;
3. a versão nova é menor ou de correção (ex.: 0.2.0 → 0.3.0). Versão **maior** (0.x → 1.0)
   sempre pede o seu "sim";
4. já passou o tempo de espera depois da publicação (`espera_horas`, padrão 48 h). Se a
   release tiver um defeito, dá tempo de sair a correção;
5. está dentro da janela de horário (`janela`, ex.: `"02:00-05:00"`).

Depois de instalar, é só reiniciar (`optimus startup restart`, se ele inicia com o PC).

## Publicar uma versão (para quem mantém o projeto)

1. Suba a versão em `optimus/__init__.py` e `pyproject.toml`.
2. `git tag v0.3.0 && git push --tags`.
3. O workflow **Release** confere se a tag bate com a versão, roda os testes, monta
   `optimus-v0.3.0.zip`, o pacote wheel e o `SHA256SUMS`, e publica a release. Tags com hífen
   (`v0.3.0-beta.1`) saem como pré-lançamento, só para o canal beta.

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
# Repositório de onde vêm as releases.
github = "Edton180/Open-Optimus-IA-Assistente-"
# "estavel" ou "beta".
canal = "estavel"
# Instalar sozinho versões menores e de correção.
automatico = false
# Esperar este tempo depois de publicada.
espera_horas = 48
# Horário permitido para instalar sozinho ("" = qualquer hora).
janela = ""
```
