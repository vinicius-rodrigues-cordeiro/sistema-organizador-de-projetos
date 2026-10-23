"""ProjetoBuilder. Padrão criacional: BUILDER.

Monta o projeto passo a passo: só o nome é obrigatório, o resto é opcional.
"""
from modelo import Projeto, Fase, Tarefa, ErroValidacao, novo_id


def texto(valor, campo, obrigatorio=False):
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        raise ErroValidacao(f"O campo '{campo}' deve ser texto.")
    valor = valor.strip()
    if obrigatorio and not valor:
        raise ErroValidacao(f"O campo '{campo}' é obrigatório.")
    return valor


def normalizar_pessoas(lista):
    if not isinstance(lista, list):
        raise ErroValidacao("O campo 'pessoas' deve ser uma lista.")
    pessoas = []
    for p in lista:
        if not isinstance(p, dict):
            raise ErroValidacao("Cada pessoa deve ter nome e cargo.")
        pessoas.append({"nome": texto(p.get("nome"), "nome da pessoa", obrigatorio=True),
                        "cargo": texto(p.get("cargo"), "cargo")})
    return pessoas


class ProjetoBuilder:
    def __init__(self, nome):
        self._nome = nome
        self._descricao = ""
        self._responsavel = ""
        self._pessoas = []
        self._fases = []

    def com_descricao(self, descricao):
        self._descricao = texto(descricao, "descricao")
        return self

    def com_responsavel(self, responsavel):
        self._responsavel = texto(responsavel, "responsavel")
        return self

    def com_pessoas(self, pessoas):
        self._pessoas = normalizar_pessoas(pessoas)
        return self

    def com_fase(self, nome, tarefas=None):
        if tarefas is None:
            tarefas = []
        if not isinstance(tarefas, list):
            raise ErroValidacao("O campo 'tarefas' deve ser uma lista.")
        self._fases.append((texto(nome, "nome da fase", obrigatorio=True),
                            [texto(t, "nome da tarefa", obrigatorio=True) for t in tarefas]))
        return self

    def construir(self):
        nome = texto(self._nome, "nome", obrigatorio=True)
        projeto = Projeto(novo_id(), nome, self._descricao, self._responsavel, self._pessoas)
        for nome_fase, tarefas in self._fases:
            fase = Fase(novo_id(), nome_fase)
            for nome_tarefa in tarefas:
                fase.adicionar(Tarefa(novo_id(), nome_tarefa))
            projeto.adicionar(fase)
        return projeto