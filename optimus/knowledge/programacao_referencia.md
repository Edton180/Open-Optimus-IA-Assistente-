# Referência de programação

Comandos e lembretes rápidos de Git, Linux, Python e expressões regulares.

## Git

- `git status` mostra o que mudou. `git add .` prepara as mudanças. `git commit -m "mensagem"`
  grava. `git push` envia para o servidor; `git pull` traz o que mudou lá.
- `git log --oneline` mostra o histórico resumido. `git diff` mostra as mudanças não preparadas.
- `git checkout -b nova-branch` cria e troca para uma ramificação. `git switch principal` volta.
- `git merge outra-branch` junta outra ramificação na atual.
- `git restore arquivo` descarta mudanças de um arquivo. `git revert COMMIT` desfaz um commit com
  um novo commit (seguro para histórico já enviado).
- `git clone URL` baixa um repositório pela primeira vez.

## Linux (terminal)

- `ls` lista arquivos; `ls -la` mostra ocultos e detalhes. `cd pasta` entra; `cd ..` sobe.
- `pwd` mostra a pasta atual. `mkdir nome` cria pasta. `rm arquivo` apaga; `rm -r pasta` apaga
  recursivo (cuidado). `cp origem destino` copia; `mv origem destino` move ou renomeia.
- `cat arquivo` mostra o conteúdo. `grep "texto" arquivo` procura. `find . -name "*.py"` busca.
- `chmod +x script.sh` dá permissão de execução. `top` ou `htop` mostra uso de CPU e memória.
- `df -h` mostra espaço em disco; `free -h` mostra memória. `ps aux` lista processos.

## Python

- Ambiente virtual: `python -m venv .venv` e depois `. .venv/bin/activate` (Linux/Mac) ou
  `.venv\Scripts\activate` (Windows). Instalar pacote: `pip install nome`.
- Rodar testes com pytest: `python -m pytest -q`. Rodar um arquivo: `python arquivo.py`.
- Listas: `[x for x in lista if cond]`. Dicionários: `{chave: valor}`. f-string: `f"{variavel}"`.
- Abrir arquivo com segurança: `with open("a.txt") as f: dados = f.read()`.
- Tratar erro: `try: ... except ValueError as e: ...`.

## Expressões regulares (regex)

- `.` qualquer caractere. `\d` dígito. `\w` letra/número/underscore. `\s` espaço.
- `*` zero ou mais. `+` um ou mais. `?` zero ou um. `{2,4}` de 2 a 4 repetições.
- `^` início da linha. `$` fim da linha. `[abc]` um dos caracteres. `[^abc]` nenhum deles.
- `(grupo)` captura. `a|b` a ou b. Escape um caractere especial com `\`, por exemplo `\.`.
- Exemplo de e-mail simples: `\w+@\w+\.\w+`.

## Boas práticas

- Nomes claros valem mais que comentários. Funções curtas, uma responsabilidade cada.
- Commits pequenos com mensagem no tempo presente ("adiciona", "corrige").
- Escreva testes para o que pode quebrar. Rode-os antes de enviar.
