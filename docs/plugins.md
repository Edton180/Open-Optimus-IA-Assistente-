# Plugins: novas habilidades

Qualquer arquivo `.py` na pasta `plugins` (dentro da pasta do Optimus: `~/.config/optimus/plugins` no
Linux, `%APPDATA%\Optimus\plugins` no Windows) é carregado ao iniciar.

```python
# plugins/cotacao.py
import httpx

from optimus.safety import LIVRE
from optimus.tools.base import ferramenta, texto


@ferramenta(
    "cotacao_moeda",
    "Cotação atual de uma moeda em reais (ex.: USD, EUR, BTC).",
    {"moeda": texto("Código da moeda")},
    risco=LIVRE,
)
def cotacao_moeda(ctx, moeda: str):
    dados = httpx.get(f"https://economia.awesomeapi.com.br/json/last/{moeda}-BRL", timeout=10).json()
    item = next(iter(dados.values()))
    return {"moeda": moeda, "compra": item["bid"], "venda": item["ask"]}
```

Reinicie o Optimus e peça: *"quanto está o dólar?"*.

## Regras

- O primeiro parâmetro é sempre `ctx` (configuração, banco, pasta de trabalho).
- Devolva um `dict` (vira JSON para o modelo) ou um texto.
- Descreva bem a ferramenta: é a descrição que faz o modelo saber quando usá-la.
- Defina o `risco`: `LIVRE`, `MODERADO`, `CRITICO`, ou uma função `(argumentos, ctx) -> Avaliacao`
  para decidir pelo conteúdo (veja `optimus/tools/arquivos.py`).
- Erros viram mensagens para o modelo, sem derrubar o Optimus.

Para desligar todos os plugins: `optimus config ferramentas.plugins false`.
