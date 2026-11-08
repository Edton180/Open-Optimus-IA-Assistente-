#!/data/data/com.termux/files/usr/bin/bash
# Instalador do Optimus no Android, dentro do Termux (https://termux.dev, baixe pelo F-Droid).
# Instale também o app "Termux:API" para o Optimus ouvir e falar pelo celular.
set -euo pipefail

PASTA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "== Instalando o Optimus no Android (Termux) =="

pkg update -y
pkg install -y python termux-api git ffmpeg
# Motor de IA local no próprio celular (funciona em aparelhos com 6 GB de RAM ou mais)
pkg install -y ollama || echo "! Ollama não disponível neste aparelho: use um PC da casa como destino (docs/rede.md)."

pip install --upgrade pip
pip install "$PASTA[documentos]"
pip install edge-tts || true

mkdir -p "$HOME/.shortcuts"
cat > "$HOME/.shortcuts/Optimus" <<'ATALHO'
#!/data/data/com.termux/files/usr/bin/bash
(ollama serve >/dev/null 2>&1 &)
optimus gui
ATALHO
chmod +x "$HOME/.shortcuts/Optimus"

if command -v ollama >/dev/null; then
  (ollama serve >/dev/null 2>&1 &) ; sleep 3
  optimus instalar-modelo || echo "! Rode depois: optimus instalar-modelo"
fi

echo
echo "✓ Pronto! Rode: optimus gui   e abra http://127.0.0.1:8765 no navegador do celular."
echo "  Voz: o Optimus usa o reconhecimento e a voz do próprio Android (Termux:API)."
echo "  Dica: no Chrome, menu > 'Adicionar à tela inicial' vira um app."
echo "Aviso: o Optimus executa ações reais no aparelho. O uso é de sua responsabilidade."
