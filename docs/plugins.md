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


## Conectar outros apps por MCP

Além de plugins em Python, o Optimus fala **MCP** (Model Context Protocol). Qualquer serviço com
servidor MCP (GitHub, Notion, Zapier, Google Drive, bancos de dados, o sistema de arquivos...)
vira ferramenta do Optimus, sem escrever código:

```toml
[[mcp]]
nome = "arquivos"
comando = ["npx", "-y", "@modelcontextprotocol/server-filesystem", "C:/Users/eu/Documentos"]

[[mcp]]
nome = "notion"
url = "https://exemplo.com/mcp"
token = "cofre:mcp.notion.token"   # guarde com: optimus chaves definir mcp.notion.token
risco = "critico"                  # livre | moderado (padrão) | critico (pede confirmação)
```

- `comando` roda um servidor local; `url` fala com um servidor remoto (HTTP).
- Teste com `optimus mcp`: ele conecta e lista as ferramentas de cada servidor.
- Cada ferramenta aparece como `mcp_<servidor>_<ferramenta>`. Para o modelo usar, cite o
  servidor no pedido: *"procura no notion a ata de ontem"*.
- Um servidor que não abrir é pulado, com aviso no log; o Optimus abre normalmente.
- Por segurança, ferramentas MCP são **moderadas** por padrão. Use `risco = "critico"` para
  servidores que mexem em coisas importantes.
