"""ControladorCliente: liga a interface ao servidor. As janelas só chamam métodos daqui
e escutam sinais daqui; nunca falam com a rede diretamente."""
import time
from enum import Enum

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class EstadoConexao(Enum):
    CARREGANDO = "carregando servidor"
    CONECTADO = "conectado"
    SEM_CONEXAO = "sem conexão com servidor"


class Atualizador(QObject):
    """Pergunta ao servidor, de tempos em tempos, o que mudou."""
    respondeu = pyqtSignal()
    sem_conexao = pyqtSignal()
    novidades = pyqtSignal(list)

    def __init__(self, api, intervalo_ms=2000):
        super().__init__()
        self.api = api
        self.ultima = None          # última versão vista
        self._ocupado = False
        self.timer = QTimer(self)
        self.timer.setInterval(intervalo_ms)
        self.timer.timeout.connect(self.consultar)

    def iniciar(self):
        self.timer.start()
        self.consultar()

    def consultar(self):
        if self._ocupado:
            return
        self._ocupado = True
        self.api.requisitar("GET", f"/atualizacoes?desde={self.ultima or 0}", callback=self._resposta)

    def _resposta(self, status, dados):
        self._ocupado = False
        if status == 0:
            self.sem_conexao.emit()
            return
        if status != 200 or not isinstance(dados, dict):
            return
        primeira = self.ultima is None
        self.ultima = dados["versao"]
        self.respondeu.emit()
        if not primeira and dados["eventos"]:
            self.novidades.emit(dados["eventos"])


class ControladorCliente(QObject):
    estado_mudou = pyqtSignal(object)
    projetos_mudaram = pyqtSignal(list)
    projeto_mudou = pyqtSignal(dict)
    projeto_removido = pyqtSignal(str)
    novidade = pyqtSignal(str)
    aviso = pyqtSignal(str)
    erro = pyqtSignal(str)
    nao_autorizado = pyqtSignal(str)

    def __init__(self, api, usuario):
        super().__init__()
        self.api = api
        self.usuario = usuario
        self.projeto = None                      # projeto aberto (dict)
        self._mutando = False                    # evita dois cliques seguidos com versão velha
        self.estado = EstadoConexao.CARREGANDO
        self.atualizador = Atualizador(api)
        self.atualizador.respondeu.connect(self._servidor_ok)
        self.atualizador.sem_conexao.connect(lambda: self._mudar_estado(EstadoConexao.SEM_CONEXAO))
        self.atualizador.novidades.connect(self._novidades)

    # ---------- conexão ----------
    def iniciar(self):
        self._inicio = time.monotonic()
        self._tentar_saude()

    def _tentar_saude(self):
        self.api.requisitar("GET", "/saude", callback=self._resposta_saude)

    def _resposta_saude(self, status, dados):
        if status == 200:
            self._servidor_ok()
            self.atualizador.iniciar()
            return
        if time.monotonic() - self._inicio >= 10:
            self._mudar_estado(EstadoConexao.SEM_CONEXAO)
        QTimer.singleShot(1000, self._tentar_saude)

    def _servidor_ok(self):
        if self.estado != EstadoConexao.CONECTADO:
            self._mudar_estado(EstadoConexao.CONECTADO)
            self.recarregar()

    def _mudar_estado(self, estado):
        if estado != self.estado:
            self.estado = estado
            self.estado_mudou.emit(estado)

    # ---------- tratamento comum das respostas ----------
    def _tratar(self, status, dados, ao_sucesso=None):
        mensagem = dados.get("erro") if isinstance(dados, dict) else None
        if status == 0:
            self._mudar_estado(EstadoConexao.SEM_CONEXAO)
            self.erro.emit("Sem conexão com o servidor.")
        elif status == 401:
            self.nao_autorizado.emit(mensagem or "Usuário não autorizado.")
        elif status == 409:
            self.aviso.emit(mensagem or "Conflito de versão.")
            self.recarregar()
        elif status >= 400:
            self.erro.emit(mensagem or f"Erro {status} no servidor.")
        elif ao_sucesso:
            ao_sucesso(dados)

    def _novidades(self, eventos):
        de_outros = [e for e in eventos if e["autor"] != self.usuario]
        if de_outros:
            ultimo = de_outros[-1]
            self.novidade.emit(f"{ultimo['autor']} {ultimo['acao']}")
            self.carregar_projetos()
            if self.projeto and any(e["projeto_id"] == self.projeto["id"] for e in de_outros):
                self.abrir_projeto(self.projeto["id"])

    # ---------- projetos ----------
    def recarregar(self):
        self.carregar_projetos()
        if self.projeto:
            self.abrir_projeto(self.projeto["id"])

    def carregar_projetos(self):
        self.api.requisitar("GET", "/projetos", callback=lambda s, d: self._tratar(
            s, d, lambda lista: self.projetos_mudaram.emit(lista)))

    def abrir_projeto(self, projeto_id, ao_sucesso=None):
        def resposta(status, dados):
            if status == 404:
                self.projeto = None
                self.projeto_removido.emit(projeto_id)
                self.carregar_projetos()
                return

            def ok(projeto):
                self._definir_projeto(projeto, recarregar_lista=False)
                if ao_sucesso:
                    ao_sucesso(projeto)
            self._tratar(status, dados, ok)
        self.api.requisitar("GET", f"/projetos/{projeto_id}", callback=resposta)

    def _definir_projeto(self, projeto, recarregar_lista=True):
        self.projeto = projeto
        self.projeto_mudou.emit(projeto)
        if recarregar_lista:
            self.carregar_projetos()

    def criar_projeto(self, dados, ao_sucesso=None):
        def ok(projeto):
            self.carregar_projetos()
            if ao_sucesso:
                ao_sucesso(projeto)
        self.api.requisitar("POST", "/projetos", dados, lambda s, d: self._tratar(s, d, ok))

    def excluir_projeto(self, projeto_id, versao):
        def ok(_):
            if self.projeto and self.projeto["id"] == projeto_id:
                self.projeto = None
                self.projeto_removido.emit(projeto_id)
            self.carregar_projetos()
        self.api.requisitar("DELETE", f"/projetos/{projeto_id}?versao={versao}",
                            callback=lambda s, d: self._tratar(s, d, ok))

    # ---------- itens e dependências (sempre sobre o projeto aberto) ----------
    def _mutar(self, metodo, caminho, corpo=None):
        if self._mutando:
            return

        def resposta(status, dados):
            self._mutando = False
            self._tratar(status, dados, self._definir_projeto)
        self._mutando = True
        self.api.requisitar(metodo, caminho, corpo, resposta)

    def criar_item(self, tipo, nome, pai_id=None, responsavel=""):
        p = self.projeto
        self._mutar("POST", f"/projetos/{p['id']}/itens",
                    {"tipo": tipo, "nome": nome, "pai_id": pai_id,
                     "responsavel": responsavel, "versao": p["versao"]})

    def renomear_item(self, item_id, nome, responsavel=None):
        corpo = {"nome": nome, "versao": self.projeto["versao"]}
        if responsavel is not None:          # só tarefas têm responsável
            corpo["responsavel"] = responsavel
        self._mutar("PUT", f"/itens/{item_id}", corpo)

    def mudar_percentual(self, item_id, percentual):
        self._mutar("PUT", f"/itens/{item_id}/status",
                    {"percentual": percentual, "versao": self.projeto["versao"]})

    def excluir_item(self, item_id):
        self._mutar("DELETE", f"/itens/{item_id}?versao={self.projeto['versao']}")

    def adicionar_dependencia(self, origem_id, destino_id):
        p = self.projeto
        self._mutar("POST", "/dependencias", {"projeto_id": p["id"], "origem_id": origem_id,
                                              "destino_id": destino_id, "versao": p["versao"]})

    def remover_dependencia(self, dependencia_id):
        self._mutar("DELETE", f"/dependencias/{dependencia_id}?versao={self.projeto['versao']}")