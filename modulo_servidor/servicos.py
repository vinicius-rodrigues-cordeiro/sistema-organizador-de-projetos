"""Regras de negócio e validações."""
from modelo import (Projeto, Fase, Tarefa, Composto, ErroValidacao, ErroNaoEncontrado,
                    STATUS_VALIDOS, novo_id)
from builder import ProjetoBuilder, texto, normalizar_pessoas


class ServicoProjetos:
    def __init__(self, mediador, repositorio):
        self.mediador = mediador
        self.repositorio = repositorio

    # ---------- leitura ----------
    def listar(self):
        return [{"id": p["id"], "nome": p["nome"], "responsavel": p.get("responsavel", ""),
                 "versao": p["versao"], "progresso": p["progresso"]}
                for p in self.repositorio.carregar()["projetos"]]

    def obter(self, projeto_id):
        for p in self.repositorio.carregar()["projetos"]:
            if p["id"] == projeto_id:
                return p
        raise ErroNaoEncontrado("Projeto não encontrado.")

    def projeto_do_item(self, item_id):
        for d in self.repositorio.carregar()["projetos"]:
            projeto = Projeto.de_dict(d)
            if projeto.buscar(item_id) is not None:
                return projeto.id
        raise ErroNaoEncontrado("Item não encontrado.")

    # ---------- projeto ----------
    def criar(self, usuario, corpo):
        builder = ProjetoBuilder(corpo.get("nome"))
        builder.com_descricao(corpo.get("descricao")).com_responsavel(corpo.get("responsavel"))
        if "pessoas" in corpo:
            builder.com_pessoas(corpo["pessoas"])
        fases = corpo.get("fases") or []
        if not isinstance(fases, list):
            raise ErroValidacao("O campo 'fases' deve ser uma lista.")
        for f in fases:
            if not isinstance(f, dict):
                raise ErroValidacao("Cada fase deve ter nome e tarefas.")
            builder.com_fase(f.get("nome"), f.get("tarefas"))
        return self.mediador.criar(usuario, builder.construir()).para_dict()

    def editar(self, usuario, projeto_id, corpo, versao):
        novo = {}
        if "nome" in corpo:
            novo["nome"] = texto(corpo["nome"], "nome", obrigatorio=True)
        if "descricao" in corpo:
            novo["descricao"] = texto(corpo["descricao"], "descricao")
        if "responsavel" in corpo:
            novo["responsavel"] = texto(corpo["responsavel"], "responsavel")
        if "pessoas" in corpo:
            novo["pessoas"] = normalizar_pessoas(corpo["pessoas"])

        def mutacao(projeto):
            for campo, valor in novo.items():
                setattr(projeto, campo, valor)
        return self.mediador.alterar(usuario, "editou o projeto", projeto_id, versao, mutacao).para_dict()

    def excluir(self, usuario, projeto_id, versao):
        self.mediador.excluir(usuario, projeto_id, versao)

    # ---------- itens (fases e tarefas) ----------
    def criar_item(self, usuario, projeto_id, corpo, versao):
        tipo = corpo.get("tipo")
        nome = texto(corpo.get("nome"), "nome", obrigatorio=True)
        responsavel = texto(corpo.get("responsavel"), "responsavel")
        pai_id = corpo.get("pai_id")
        if tipo not in ("fase", "tarefa"):
            raise ErroValidacao("O campo 'tipo' deve ser 'fase' ou 'tarefa'.")

        def mutacao(projeto):
            pai = projeto if pai_id is None else projeto.buscar(pai_id)
            if pai is None:
                raise ErroNaoEncontrado("Fase pai não encontrada.")
            if not isinstance(pai, Composto):
                raise ErroValidacao("Uma tarefa não pode conter outros itens.")
            if tipo == "tarefa" and pai is projeto:
                raise ErroValidacao("Toda tarefa deve ficar dentro de uma fase. Crie uma fase primeiro.")
            if tipo == "fase":
                pai.adicionar(Fase(novo_id(), nome))
            else:
                pai.adicionar(Tarefa(novo_id(), nome, responsavel=responsavel))
        return self.mediador.alterar(usuario, f"criou {tipo} '{nome}'", projeto_id, versao, mutacao).para_dict()

    def editar_item(self, usuario, item_id, corpo, versao):
        nome = texto(corpo["nome"], "nome", obrigatorio=True) if "nome" in corpo else None
        responsavel = texto(corpo["responsavel"], "responsavel") if "responsavel" in corpo else None

        def mutacao(projeto):
            item = projeto.buscar(item_id)
            if item is None:
                raise ErroNaoEncontrado("Item não encontrado.")
            if nome is not None:
                item.nome = nome
            if responsavel is not None and isinstance(item, Tarefa):
                item.responsavel = responsavel
        return self.mediador.alterar(usuario, "editou um item", self.projeto_do_item(item_id),
                                     versao, mutacao).para_dict()

    def mudar_status(self, usuario, item_id, corpo, versao):
        percentual = self._percentual(corpo)

        def mutacao(projeto):
            item = projeto.buscar(item_id)
            if item is None:
                raise ErroNaoEncontrado("Item não encontrado.")
            if not isinstance(item, Tarefa):
                raise ErroValidacao("Só tarefas têm status.")
            item.percentual = percentual
        return self.mediador.alterar(usuario, f"colocou uma tarefa em {percentual}%",
                                     self.projeto_do_item(item_id), versao, mutacao).para_dict()

    @staticmethod
    def _percentual(corpo):
        """Aceita 'percentual' (0 a 100, de 10 em 10) ou o 'status' antigo."""
        if "percentual" in corpo:
            p = corpo["percentual"]
            if isinstance(p, bool) or not isinstance(p, int) or p < 0 or p > 100 or p % 10 != 0:
                raise ErroValidacao("O percentual deve ser de 0 a 100, de 10 em 10.")
            return p
        status = corpo.get("status")
        if status not in STATUS_VALIDOS:
            raise ErroValidacao(f"Status inválido. Use: {', '.join(STATUS_VALIDOS)}.")
        return {"pendente": 0, "em_andamento": 10, "concluida": 100}[status]

    def excluir_item(self, usuario, item_id, versao):
        def mutacao(projeto):
            item = projeto.remover(item_id)
            if item is None:
                raise ErroNaoEncontrado("Item não encontrado.")
            ids = {t.id for t in item.tarefas()} if isinstance(item, Composto) else {item.id}
            # decisão: dependências que envolvem tarefas removidas somem junto
            projeto.dependencias = [d for d in projeto.dependencias
                                    if d["origem_id"] not in ids and d["destino_id"] not in ids]
        return self.mediador.alterar(usuario, "excluiu um item", self.projeto_do_item(item_id),
                                     versao, mutacao).para_dict()


class ServicoDependencias:
    """origem depende de destino."""

    def __init__(self, mediador, repositorio):
        self.mediador = mediador
        self.repositorio = repositorio

    @staticmethod
    def _alcanca(dependencias, inicio, alvo):
        visitados, pilha = set(), [inicio]
        while pilha:
            atual = pilha.pop()
            if atual == alvo:
                return True
            if atual in visitados:
                continue
            visitados.add(atual)
            pilha.extend(d["destino_id"] for d in dependencias if d["origem_id"] == atual)
        return False

    def adicionar(self, usuario, corpo, versao):
        projeto_id = corpo.get("projeto_id")
        origem, destino = corpo.get("origem_id"), corpo.get("destino_id")

        def mutacao(projeto):
            if origem == destino:
                raise ErroValidacao("Uma tarefa não pode depender dela mesma.")
            o, d = projeto.buscar(origem), projeto.buscar(destino)
            if not isinstance(o, Tarefa) or not isinstance(d, Tarefa):
                raise ErroValidacao("As duas pontas da dependência devem ser tarefas existentes do projeto.")
            if any(x["origem_id"] == origem and x["destino_id"] == destino for x in projeto.dependencias):
                raise ErroValidacao("Essa dependência já existe.")
            if self._alcanca(projeto.dependencias, destino, origem):
                raise ErroValidacao("Essa dependência criaria um ciclo.")
            projeto.dependencias.append({"id": novo_id(), "origem_id": origem, "destino_id": destino})
        return self.mediador.alterar(usuario, "adicionou uma dependência", projeto_id,
                                     versao, mutacao).para_dict()

    def remover(self, usuario, dependencia_id, versao):
        projeto_id = None
        for p in self.repositorio.carregar()["projetos"]:
            if any(d["id"] == dependencia_id for d in p["dependencias"]):
                projeto_id = p["id"]
        if projeto_id is None:
            raise ErroNaoEncontrado("Dependência não encontrada.")

        def mutacao(projeto):
            projeto.dependencias = [d for d in projeto.dependencias if d["id"] != dependencia_id]
        return self.mediador.alterar(usuario, "removeu uma dependência", projeto_id,
                                     versao, mutacao).para_dict()