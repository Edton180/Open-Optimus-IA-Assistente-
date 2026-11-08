# Instalação

## Requisitos

| | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10, Linux 64 bits, Android 9 (Termux) | Windows 11, Ubuntu 22.04+ |
| Python | 3.10 | 3.12 |
| RAM | 4 GB | 16 GB ou mais |
| Placa de vídeo | não precisa | NVIDIA ou AMD com 8 GB+ de VRAM |
| Disco | 3 GB (modelo pequeno + vozes) | 20 GB para modelos maiores |

O Optimus escolhe o modelo pelo que o PC tem. Em PCs fracos ele usa modelos pequenos e contexto menor;
em PCs fortes, modelos maiores e a placa de vídeo. Veja os perfis em [motor.md](motor.md).

## Windows 10 e 11

1. Baixe o projeto: `git clone https://github.com/Edton180/Open-Optimus-IA-Assistente-.git optimus`
   (ou baixe o ZIP pelo botão verde **Code** e extraia).
2. Abra o PowerShell na pasta e rode:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
   ```

O instalador:

- instala o Python 3.12 pelo `winget` se não houver;
- cria o ambiente em `%LOCALAPPDATA%\Optimus` e o comando `optimus`;
- baixa as **vozes naturais offline** (Dora, Alex e Santa, cerca de 120 MB);
- instala o **Ollama** pelo `winget`, detecta o hardware e baixa o modelo ideal;
- cria o atalho **Optimus** na área de trabalho e no menu Iniciar.

As vozes do Windows (Maria, Daniel) também funcionam sem baixar nada. Para ter mais vozes do sistema em
português: Configurações > Hora e idioma > Fala > Adicionar vozes.

## Linux

```bash
git clone https://github.com/Edton180/Open-Optimus-IA-Assistente-.git optimus
cd optimus
bash scripts/instalar.sh
```

O instalador usa `apt`, `dnf` ou `pacman` para instalar Python, PortAudio (microfone), espeak-ng e ffmpeg,
cria o ambiente em `~/.local/share/optimus`, o comando `~/.local/bin/optimus`, baixa as vozes, instala o
Ollama e o modelo, e cria o atalho no menu de aplicativos. Use `--sem-ia` para pular o Ollama.

## Android (Termux)

1. Instale o **Termux** e o **Termux:API** pelo [F-Droid](https://f-droid.org) (a versão da Play Store é antiga).
2. No Termux:

   ```bash
   pkg install git
   git clone https://github.com/Edton180/Open-Optimus-IA-Assistente-.git optimus
   cd optimus && bash scripts/instalar-android.sh
   ```

3. Rode `optimus gui` e abra `http://127.0.0.1:8765` no Chrome. No menu do Chrome, **Adicionar à tela
   inicial** cria um ícone como se fosse um app.

No Android o Optimus usa o reconhecimento de voz e a voz do próprio celular (Termux:API). Celulares com
6 GB de RAM ou mais conseguem rodar modelos pequenos com o Ollama do Termux. Em aparelhos mais simples,
use o celular como controle remoto de um PC da casa (abaixo) ou configure um destino na nuvem
([rede.md](rede.md)).

> O suporte ao Android é feito pelo Termux. As funções de controle de PC (programas, teclado e mouse,
> energia) não se aplicam ao celular.

## Usar pelo celular, com o Optimus rodando no PC

No PC:

```bash
optimus config web.senha UMA_SENHA_FORTE
optimus gui --rede
```

No celular (mesmo Wi-Fi), abra `http://IP-DO-PC:8765` e digite a senha. O microfone do celular funciona
na interface: segure o botão 🎙️ para falar.

## Instalação manual (qualquer sistema)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install ".[completo]"      # ou só "." para o básico, sem voz
optimus vozes --baixar          # vozes offline
# instale o Ollama em https://ollama.com e depois:
optimus instalar-modelo
optimus gui
```

Extras disponíveis: `voz`, `desktop` (teclado, mouse, prints), `casa` (Bluetooth), `documentos` (PDF),
`completo` (todos), `dev` (testes).

## Atualizar

```bash
cd optimus
git pull
# Linux:   ~/.local/share/optimus/venv/bin/pip install ".[completo]"
# Windows: %LOCALAPPDATA%\Optimus\venv\Scripts\pip install ".[completo]"
```

Conversas, memória, lembretes e configurações ficam em `~/.config/optimus` (Linux) ou
`%APPDATA%\Optimus` (Windows) e não são apagados na atualização.
