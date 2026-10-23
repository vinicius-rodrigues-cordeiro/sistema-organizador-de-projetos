"""Padrão comportamental: MEDIATOR.

O MediadorColaboracao coordena ControleDeVersao, FeedDeAtualizacoes e o repositório.
Eles não se chamam entre si; quem conversa com todos é o mediador.
Cada alteração é uma transação: uma de cada vez, e só confirma se gravou.
"""
import threading
from datetime import datetime

from modelo import Projeto, ErroConflito, ErroNaoEncontrado, ErroValidacao


class Mediador:
    def alterar(self, usuario, acao, projeto_id, versao, mutacao):
        raise NotImplementedError


class ControleDeVersao:
    def verificar(self, projeto_dict, versao_enviada, ultimo_autor):
        if versao_enviada is None:
            raise ErroValidacao("A versão do projeto é obrigatória.")
        if versao_enviada != projeto_dict["versao"]:
            raise ErroConflito(f"O projeto foi alterado por {ultimo_autor or 'outro usuário'}. "
                               "Recarregue antes de salvar.")


class FeedDeAtualizacoes:
    def registrar(self, dados, projeto_id, autor, acao):
        dados["eventos"].append({"versao": dados["versao"], "projeto_id": projeto_id,
                                 "autor": autor, "acao": acao,
                                 "hora": datetime.now().strftime("%H:%M:%S")})
        dados["eventos"] = dados["eventos"][-100:]

    def desde(self, dados, versao):
        return [e for e in dados["eventos"] if e["versao"] > versao]

    def ultimo_autor(self, dados, projeto_id):
        for e in reversed(dados["eventos"]):
            if e["projeto_id"] == projeto_id:
                return e["autor"]
        return None


class MediadorColaboracao(Mediador):
    def __init__(self, repositorio):
        self.repositorio = repositorio
        self.versoes = ControleDeVersao()
        self.feed = FeedDeAtualizacoes()
        self._trava = threading.Lock()

    def _achar(self, dados, projeto_id):
        for i, p in enumerate(dados["projetos"]):
            if p["id"] == projeto_id:
                return i, p
        raise ErroNaoEncontrado("Projeto não encontrado.")

    def criar(self, usuario, projeto):
        with self._trava:
            dados = self.repositorio.carregar()
            dados["versao"] += 1
            projeto.versao = dados["versao"]
            dados["projetos"].append(projeto.para_dict())
            self.feed.registrar(dados, projeto.id, usuario, f"criou o projeto '{projeto.nome}'")
            self.repositorio.salvar(dados)
            return projeto

    def alterar(self, usuario, acao, projeto_id, versao, mutacao):
        with self._trava:
            dados = self.repositorio.carregar()
            i, atual = self._achar(dados, projeto_id)
            self.versoes.verificar(atual, versao, self.feed.ultimo_autor(dados, projeto_id))
            projeto = Projeto.de_dict(atual)
            mutacao(projeto)                      # pode levantar erro de validação
            dados["versao"] += 1
            projeto.versao = dados["versao"]
            dados["projetos"][i] = projeto.para_dict()
            self.feed.registrar(dados, projeto_id, usuario, acao)
            self.repositorio.salvar(dados)        # só confirma depois de gravar
            return projeto

    def excluir(self, usuario, projeto_id, versao):
        with self._trava:
            dados = self.repositorio.carregar()
            i, atual = self._achar(dados, projeto_id)
            self.versoes.verificar(atual, versao, self.feed.ultimo_autor(dados, projeto_id))
            dados["versao"] += 1
            del dados["projetos"][i]
            self.feed.registrar(dados, projeto_id, usuario, f"excluiu o projeto '{atual['nome']}'")
            self.repositorio.salvar(dados)

    def atualizacoes(self, desde):
        dados = self.repositorio.carregar()
        return {"versao": dados["versao"], "eventos": self.feed.desde(dados, desde)}