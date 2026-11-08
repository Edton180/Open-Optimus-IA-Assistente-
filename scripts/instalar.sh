#!/usr/bin/env bash
# Instalador do Optimus para Linux (Ubuntu, Debian, Mint, Fedora, Arch...) e Android (Termux).
#   bash scripts/instalar.sh            instala tudo
#   bash scripts/instalar.sh --sem-ia   não instala o Ollama nem baixa o modelo
set -euo pipefail

VERDE='\033[92m'; AMARELO='\033[93m'; VERMELHO='\033[91m'; NORMAL='\033[0m'
ok()    { echo -e "${VERDE}✓${NORMAL} $*"; }
aviso() { echo -e "${AMARELO}!${NORMAL} $*"; }
erro()  { echo -e "${VERMELHO}✗${NORMAL} $*"; exit 1; }

PASTA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEM_IA=0
[[ "${1:-}" == "--sem-ia" ]] && SEM_IA=1

if [[ -n "${PREFIX:-}" && "$PREFIX" == *com.termux* ]]; then
  exec bash "$PASTA/scripts/instalar-android.sh" "$@"
fi

echo "== Instalando o Optimus =="

# 1. Python
if ! command -v python3 >/dev/null; then
  aviso "Python 3 não encontrado. Instalando..."
  if command -v apt-get >/dev/null; then sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null; then sudo dnf install -y python3 python3-pip
  elif command -v pacman >/dev/null; then sudo pacman -S --noconfirm python python-pip
  else erro "Instale o Python 3.10 ou mais novo e rode de novo."; fi
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || erro "Precisa do Python 3.10 ou mais novo."
ok "Python $(python3 --version | cut -d' ' -f2)"

# 2. Pacotes do sistema para áudio (microfone e alto-falante)
if command -v apt-get >/dev/null; then
  sudo apt-get install -y python3-venv libportaudio2 espeak-ng ffmpeg >/dev/null 2>&1 && ok "Áudio do sistema (PortAudio, espeak-ng, ffmpeg)" || aviso "Não consegui instalar os pacotes de áudio (opcional)."
elif command -v dnf >/dev/null; then
  sudo dnf install -y portaudio espeak-ng ffmpeg-free >/dev/null 2>&1 && ok "Áudio do sistema" || aviso "Pacotes de áudio não instalados (opcional)."
elif command -v pacman >/dev/null; then
  sudo pacman -S --noconfirm --needed portaudio espeak-ng ffmpeg >/dev/null 2>&1 && ok "Áudio do sistema" || aviso "Pacotes de áudio não instalados (opcional)."
fi

# 3. Ambiente do Optimus
DADOS="${XDG_DATA_HOME:-$HOME/.local/share}/optimus"
mkdir -p "$DADOS" "$HOME/.local/bin"
python3 -m venv "$DADOS/venv"
"$DADOS/venv/bin/python" -m pip install --upgrade pip >/dev/null
"$DADOS/venv/bin/python" -m pip install "$PASTA[completo]" || "$DADOS/venv/bin/python" -m pip install "$PASTA"
ln -sf "$DADOS/venv/bin/optimus" "$HOME/.local/bin/optimus"
ok "Optimus instalado (comando: optimus)"

# 4. Vozes naturais offline (feminina e masculina) já prontas
"$DADOS/venv/bin/optimus" vozes --baixar || aviso "Vozes offline não baixadas agora. Rode depois: optimus vozes --baixar"

# 5. Motor de IA local (Ollama) e modelo ideal para este PC
if [[ $SEM_IA -eq 0 ]]; then
  if ! command -v ollama >/dev/null; then
    echo "Instalando o Ollama (motor de IA local, https://ollama.com)..."
    curl -fsSL https://ollama.com/install.sh | sh || aviso "Não consegui instalar o Ollama. Instale em https://ollama.com/download"
  fi
  if command -v ollama >/dev/null; then
    (ollama serve >/dev/null 2>&1 &) ; sleep 3
    "$DADOS/venv/bin/optimus" hardware
    "$DADOS/venv/bin/optimus" instalar-modelo || aviso "Rode depois: optimus instalar-modelo"
  fi
fi

# 6. Atalho no menu de aplicativos
mkdir -p "$HOME/.local/share/applications" "$DADOS/icone"
cp "$PASTA/optimus/web/static/icone-512.png" "$DADOS/icone/optimus.png"
cat > "$HOME/.local/share/applications/optimus.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Optimus
Comment=Assistente de IA local
Exec=$DADOS/venv/bin/optimus gui
Icon=$DADOS/icone/optimus.png
Terminal=false
Categories=Utility;
DESK
ok "Atalho \"Optimus\" criado no menu de aplicativos"

# 7. Iniciar junto com o computador (remova com: optimus startup remove)
"$DADOS/venv/bin/optimus" startup install || aviso "Rode depois: optimus startup install"

echo
ok "Pronto! Abra o Optimus pelo menu ou rode:  optimus gui"
[[ ":$PATH:" != *":$HOME/.local/bin:"* ]] && aviso "Adicione ~/.local/bin ao PATH ou abra um terminal novo."
echo "Aviso: o Optimus executa ações reais no seu computador. O uso é de sua responsabilidade."
