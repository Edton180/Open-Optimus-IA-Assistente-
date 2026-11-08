"""Sub-agentes especializados.

O Optimus pode dividir um trabalho grande e entregar partes a especialistas. Cada um tem
o seu próprio prompt, só as ferramentas da sua área e o seu próprio ciclo de passos. Eles
usam as mesmas regras de confirmação do Optimus.
"""

from __future__ import annotations

from optimus.tools.base import ferramenta, texto

ESPECIALISTAS: dict[str, dict] = {
    "dev": {
        "nome": "Agente Dev",
        "grupos": {"geral", "arquivos", "comandos", "internet"},
        "codigo": True,
        "prompt": (
            "Você é o Agente Dev do Optimus, um engenheiro de software sênior. Trabalhe como "
            "um agente de programação de terminal: 1) entenda o projeto (listar_pasta, "
            "buscar_no_codigo, ler_codigo); 2) faça um plano curto; 3) edite com "
            "editar_arquivo ou crie com escrever_arquivo, em mudanças pequenas; 4) rode "
            "rodar_testes ou o programa e leia o erro; 5) corrija até funcionar. Não invente "
            "APIs: confira no código ou na documentação. No fim, liste os arquivos mudados e "
            "como testar."),
    },
    "devops": {
        "nome": "Agente DevOps",
        "grupos": {"geral", "arquivos", "comandos", "programas", "controle"},
        "codigo": True,
        "prompt": (
            "Você é o Agente DevOps do Optimus. Cuida de ambientes, dependências, Docker, git, "
            "serviços, logs e servidores. Antes de mudar algo, veja o estado atual (status, "
            "ps, logs). Prefira comandos que dá para desfazer e explique o que fez."),
    },
    "pesquisa": {
        "nome": "Agente de Pesquisa",
        "grupos": {"geral", "internet", "memoria"},
        "prompt": (
            "Você é o Agente de Pesquisa do Optimus. Pesquise em várias fontes, leia as "
            "páginas mais relevantes, compare, e entregue um resumo organizado com os links. "
            "Se achar algo que valha guardar, use aprender."),
    },
    "seguranca": {
        "nome": "Agente de Segurança",
        "grupos": {"geral", "arquivos", "comandos", "internet"},
        "prompt": (
            "Você é o Agente de Segurança defensiva do Optimus. Revise o código, as "
            "dependências e as configurações do PC do usuário em busca de falhas: senhas e "
            "chaves expostas, permissões abertas, portas e serviços desnecessários, pacotes "
            "com vulnerabilidades conhecidas, configurações fracas. Explique o risco de cada "
            "item e proponha a correção; só aplique depois que o usuário aprovar."),
    },
}


@ferramenta(
    "delegar",
    "Entrega uma parte do trabalho a um especialista e recebe o resultado: dev (programar, "
    "corrigir bugs, criar apps), devops (docker, git, servidores, dependências), pesquisa "
    "(pesquisa profunda na internet), seguranca (auditar código e configurações). Descreva a "
    "tarefa completa, com pastas e critérios de pronto.",
    {"especialista": {"type": "string", "enum": list(ESPECIALISTAS),
                      "description": "Quem vai fazer"},
     "tarefa": texto("O que fazer, com todos os detalhes")},
    grupo="geral",
)
def delegar(ctx, especialista: str, tarefa: str):
    pai = getattr(ctx, "agente", None)
    if pai is None:
        return {"erro": "Sub-agentes só funcionam dentro de uma conversa."}
    if pai.profundidade >= 1:
        return {"erro": "Um especialista não pode delegar de novo. Faça você mesmo."}
    perfil = ESPECIALISTAS.get((especialista or "").lower())
    if not perfil:
        return {"erro": f"Especialista desconhecido. Use: {', '.join(ESPECIALISTAS)}"}
    sub = pai.criar_sub_agente(perfil["nome"], perfil["grupos"])
    modelo = (pai.config.get("motor", "modelo_codigo") or "") if perfil.get("codigo") else ""
    resposta = sub.responder(tarefa, persona={"chave": especialista, "nome": perfil["nome"],
                                              "prompt": perfil["prompt"], "modelo": modelo})
    return {"especialista": perfil["nome"], "resultado": resposta}
