"""Modelo de dados. Padrão estrutural: COMPOSITE.

ItemProjeto (componente) -> Tarefa (folha) | Composto -> Fase, Projeto (compostos).
A mesma operação progresso() vale em qualquer nível da árvore.

Cada tarefa tem um percentual de 0 a 100, de 10 em 10. O status é consequência dele:
0 = pendente, 10 a 90 = em andamento, 100 = concluída. Fase e projeto mostram a média.
"""
import uuid

STATUS_VALIDOS = ("pendente", "em_andamento", "concluida")


class ErroValidacao(Exception):      # vira 422
    pass


class ErroConflito(Exception):       # vira 409
    pass


class ErroNaoEncontrado(Exception):  # vira 404
    pass


def novo_id():
    return uuid.uuid4().hex[:8]


class ItemProjeto:
    """Componente: o que tarefa, fase e projeto têm em comum."""
    tipo = "item"

    def __init__(self, id, nome):
        self.id = id
        self.nome = nome

    def contagem(self):
        """(pontos concluídos, total de tarefas): cada tarefa vale de 0 a 1 ponto."""
        raise NotImplementedError

    def progresso(self):
        feitas, total = self.contagem()
        return round(100 * feitas / total) if total else 0

    def para_dict(self):
        raise NotImplementedError


class Tarefa(ItemProjeto):
    """Folha."""
    tipo = "tarefa"

    def __init__(self, id, nome, percentual=0, responsavel=""):
        super().__init__(id, nome)
        self.percentual = percentual      # 0, 10, 20 ... 100
        self.responsavel = responsavel

    @property
    def status(self):
        if self.percentual == 0:
            return "pendente"
        return "concluida" if self.percentual == 100 else "em_andamento"

    def contagem(self):
        return self.percentual / 100, 1

    def para_dict(self):
        return {"id": self.id, "tipo": "tarefa", "nome": self.nome,
                "percentual": self.percentual, "status": self.status,
                "responsavel": self.responsavel, "progresso": self.progresso()}


class Composto(ItemProjeto):
    """Item que contém outros itens."""

    def __init__(self, id, nome):
        super().__init__(id, nome)
        self.itens = []

    def adicionar(self, item):
        self.itens.append(item)

    def contagem(self):
        feitas = total = 0
        for item in self.itens:
            f, t = item.contagem()
            feitas += f
            total += t
        return feitas, total

    def buscar(self, item_id):
        for item in self.itens:
            if item.id == item_id:
                return item
            if isinstance(item, Composto):
                achado = item.buscar(item_id)
                if achado is not None:
                    return achado
        return None

    def remover(self, item_id):
        for item in self.itens:
            if item.id == item_id:
                self.itens.remove(item)
                return item
            if isinstance(item, Composto):
                removido = item.remover(item_id)
                if removido is not None:
                    return removido
        return None

    def tarefas(self):
        achadas = []
        for item in self.itens:
            if isinstance(item, Composto):
                achadas.extend(item.tarefas())
            else:
                achadas.append(item)
        return achadas


class Fase(Composto):
    tipo = "fase"

    def para_dict(self):
        return {"id": self.id, "tipo": "fase", "nome": self.nome,
                "progresso": self.progresso(),
                "itens": [i.para_dict() for i in self.itens]}


class Projeto(Composto):
    tipo = "projeto"

    def __init__(self, id, nome, descricao="", responsavel="", pessoas=None, versao=0):
        super().__init__(id, nome)
        self.descricao = descricao
        self.responsavel = responsavel
        self.pessoas = pessoas or []      # [{"nome":..., "cargo":...}]
        self.versao = versao
        self.dependencias = []            # [{"id", "origem_id", "destino_id"}]

    def para_dict(self):
        return {"id": self.id, "nome": self.nome, "descricao": self.descricao,
                "responsavel": self.responsavel, "pessoas": self.pessoas,
                "versao": self.versao, "progresso": self.progresso(),
                "itens": [i.para_dict() for i in self.itens],
                "dependencias": self.dependencias}

    @staticmethod
    def de_dict(d):
        projeto = Projeto(d["id"], d["nome"], d.get("descricao", ""),
                          d.get("responsavel", ""), d.get("pessoas", []), d.get("versao", 0))
        projeto.itens = [_item_de_dict(i) for i in d.get("itens", [])]
        projeto.dependencias = d.get("dependencias", [])
        return projeto


def _item_de_dict(d):
    if d["tipo"] == "fase":
        fase = Fase(d["id"], d["nome"])
        fase.itens = [_item_de_dict(i) for i in d.get("itens", [])]
        return fase
    percentual = d.get("percentual")
    if percentual is None:                # dados antigos, que só tinham o status
        percentual = {"concluida": 100, "em_andamento": 10}.get(d.get("status"), 0)
    return Tarefa(d["id"], d["nome"], percentual, d.get("responsavel", ""))