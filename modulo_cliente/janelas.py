"""Interface PyQt6. As telas vêm da pasta Ui/ (Qt Designer); aqui só ligamos os botões
e ajustamos o que o Designer não cobre (árvore, textos, botões extras)."""
import json
import os

from PyQt6 import uic
from PyQt6.QtCore import QByteArray, QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtNetwork import QHostAddress, QNetworkInterface, QUdpSocket
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
                             QPushButton, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
                             QTreeWidgetItemIterator)

from api import ClienteApi
from controlador import EstadoConexao

PASTA_UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ui")
ARQUIVO_USUARIOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "dados", "usuarios.json")
PORTA_DESCOBERTA = 5001           # a mesma que o servidor usa para responder
PERGUNTA = b"ORGANIZADOR?"
MSG_SEM_ACESSO = ("Usuário não identificado ou não autorizado.\n"
                  "Entre em contato com a equipe de desenvolvimento ou com o responsável técnico Alex Torquato.")
ID, TIPO, STATUS = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1, Qt.ItemDataRole.UserRole + 2


def carregar_ui(nome, janela):
    uic.loadUi(os.path.join(PASTA_UI, nome), janela)


def perguntar(janela, titulo, texto):
    """Pergunta Sim/Não em português. Devolve True para Sim."""
    caixa = QMessageBox(QMessageBox.Icon.Question, titulo, texto, parent=janela)
    sim = caixa.addButton("Sim", QMessageBox.ButtonRole.YesRole)
    nao = caixa.addButton("Não", QMessageBox.ButtonRole.NoRole)
    caixa.setDefaultButton(sim)
    caixa.setEscapeButton(nao)
    caixa.exec()
    return caixa.clickedButton() is sim


def nome_cadastrado_na_copia_local(nome):
    """Usado só quando o servidor está fora do ar: True/False conforme a cópia local da lista
    de usuários, ou None se não houver cópia para conferir. Quem decide de verdade é o servidor."""
    try:
        with open(ARQUIVO_USUARIOS, encoding="utf-8") as arquivo:
            return nome in json.load(arquivo)["usuarios"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


class BarraDeStatus:
    """Mostra o estado da conexão e avisos rápidos."""
    CORES = {EstadoConexao.CARREGANDO: "#b8860b", EstadoConexao.CONECTADO: "#2e7d32",
             EstadoConexao.SEM_CONEXAO: "#c62828"}

    def __init__(self, barra, usuario):
        self.barra, self.usuario = barra, usuario
        self.rotulo = QLabel()
        barra.addPermanentWidget(self.rotulo)

    def mostrar(self, estado):
        texto = f"conectado como {self.usuario}" if estado == EstadoConexao.CONECTADO else estado.value
        self.rotulo.setText(texto)
        self.rotulo.setStyleSheet(f"color: {self.CORES[estado]}; font-weight: bold;")

    def aviso(self, texto):
        self.barra.showMessage(texto, 6000)

    def sem_acesso(self):
        self.rotulo.setText("usuário não autorizado")
        self.rotulo.setStyleSheet(f"color: {self.CORES[EstadoConexao.SEM_CONEXAO]}; font-weight: bold;")


class BuscadorDeServidores(QObject):
    """Pergunta na rede local quem é servidor e junta as respostas: [(nome, ip, porta), ...]."""
    terminou = pyqtSignal(list)

    def __init__(self, espera_ms=1200):
        super().__init__()
        self.espera_ms = espera_ms
        self.achados = {}
        self.soquete = QUdpSocket(self)
        self.soquete.bind(QHostAddress(QHostAddress.SpecialAddress.AnyIPv4), 0)
        self.soquete.readyRead.connect(self._ler)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._concluir)

    def buscar(self):
        self.achados = {}
        destinos = [QHostAddress(QHostAddress.SpecialAddress.Broadcast), QHostAddress("127.0.0.1")]
        for interface in QNetworkInterface.allInterfaces():
            for entrada in interface.addressEntries():
                if not entrada.broadcast().isNull():
                    destinos.append(entrada.broadcast())
        for destino in destinos:
            self.soquete.writeDatagram(QByteArray(PERGUNTA), destino, PORTA_DESCOBERTA)
        self.timer.start(self.espera_ms)

    def _ler(self):
        while self.soquete.hasPendingDatagrams():
            pacote = self.soquete.receiveDatagram()
            try:
                info = json.loads(bytes(pacote.data()).decode("utf-8"))
                if info.get("servico") != "organizador":
                    continue
                chave = (str(info["nome"]), int(info["porta"]))
            except (ValueError, KeyError, TypeError):
                continue
            ip = pacote.senderAddress().toString().replace("::ffff:", "")
            if chave not in self.achados or self.achados[chave].startswith("127."):
                self.achados[chave] = ip          # prefere o IP da rede ao 127.0.0.1

    def _concluir(self):
        self.terminou.emit(sorted((nome, ip, porta) for (nome, porta), ip in self.achados.items()))


class DialogoLogin(QDialog):
    """Pede o nome e acha o servidor sozinho; confere o nome antes de abrir o programa."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Organizador de Projetos")
        self.setMinimumWidth(460)
        self.config = QSettings("Equipe4", "OrganizadorDeProjetos")
        self.nome = QLineEdit(self._lembrado("nome", ""))
        self.servidor = QComboBox()
        self.servidor.setEditable(True)
        self.servidor.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.servidor.lineEdit().setPlaceholderText("Procurando servidor...")
        self._reserva = self._lembrado("endereco", "127.0.0.1:5000")   # usado só se nada for encontrado
        self._digitado = False                   # a pessoa mexeu no campo à mão
        self.servidor.lineEdit().textEdited.connect(lambda _: setattr(self, "_digitado", True))
        self.procurar = QPushButton("Procurar de novo")
        self.procurar.clicked.connect(self._procurar)
        self.situacao = QLabel("")
        self.situacao.setStyleSheet("color: #666666;")
        self.aviso = QLabel("")
        self.aviso.setWordWrap(True)
        form = QFormLayout(self)
        form.addRow("Seu nome:", self.nome)
        form.addRow("Servidor:", self.servidor)
        form.addRow(self.situacao)
        form.addRow(self.procurar)
        form.addRow(self.aviso)
        self.botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.botoes.accepted.connect(self._validar)
        self.botoes.rejected.connect(self.reject)
        form.addRow(self.botoes)
        self._api = None
        self.buscador = BuscadorDeServidores()
        self.buscador.terminou.connect(self._mostrar_servidores)
        self.repetir = QTimer(self)              # enquanto nenhum servidor aparece, procura de novo
        self.repetir.setInterval(2500)
        self.repetir.timeout.connect(self._procurar)
        self.finished.connect(lambda _: self.repetir.stop())
        self._procurar()
        self.repetir.start()

    # ---------- busca do servidor ----------
    def _procurar(self):
        self.situacao.setText("Procurando servidores na rede...")
        self.buscador.buscar()

    def _mostrar_servidores(self, achados):
        if not achados:
            self.situacao.setText("Nenhum servidor encontrado. Inicie o servidor (ele aparece aqui sozinho) "
                                  "ou digite o endereço.")
            if not self._digitado and self.servidor.count() == 0:
                self.servidor.addItem("Servidor", self._reserva)   # mostra só "Servidor"; o endereço fica por trás
                self.servidor.setCurrentIndex(0)
            return
        self.repetir.stop()
        atual = self.servidor.currentText()
        self.servidor.clear()
        for numero, (_, ip, porta) in enumerate(achados, start=1):
            rotulo = "Servidor" if len(achados) == 1 else f"Servidor {numero}"
            self.servidor.addItem(rotulo, f"{ip}:{porta}")
        if not self._digitado:
            self.servidor.setCurrentIndex(0)
        else:
            self.servidor.setEditText(atual)
        quantos = len(achados)
        self.situacao.setText("1 servidor encontrado." if quantos == 1
                              else f"{quantos} servidores encontrados. Escolha um na lista.")

    def endereco(self):
        """IP:porta do item escolhido na lista, ou o que a pessoa digitou."""
        i = self.servidor.currentIndex()
        if i >= 0 and self.servidor.currentText() == self.servidor.itemText(i):
            return self.servidor.itemData(i)
        return self.servidor.currentText().strip()

    # ---------- entrada ----------
    def _lembrado(self, chave, padrao):
        valor = self.config.value(chave, padrao)
        return str(valor) if valor else padrao

    def _mostrar(self, texto, erro=True):
        self.aviso.setStyleSheet("color: #c62828;" if erro else "color: #666666;")
        self.aviso.setText(texto)

    def _validar(self):
        nome, endereco = self.valores()
        if not nome:
            self._mostrar("Digite o seu nome.")
            return
        if not endereco:
            self._mostrar("Escolha o servidor na lista ou digite o endereço.")
            return
        self._mostrar("Verificando...", erro=False)
        self.botoes.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._api = ClienteApi(endereco, nome)
        self._api.requisitar("GET", "/projetos", callback=self._resposta)

    def _resposta(self, status, dados):
        self.botoes.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        if not self.isVisible():             # a pessoa cancelou enquanto verificava
            return
        nome, endereco = self.valores()
        if status == 401:
            self._mostrar(MSG_SEM_ACESSO)
            return
        if status == 0:
            if nome_cadastrado_na_copia_local(nome) is False:      # nome errado: nem pergunta
                self._mostrar(MSG_SEM_ACESSO)
                return
            if not perguntar(self, "Servidor não encontrado",
                             "Não foi possível conectar ao servidor.\n\n"
                             "Abrir mesmo assim? O programa continuará tentando conectar."):
                self._mostrar("Confira o servidor e tente de novo.")
                return
        self.config.setValue("nome", nome)
        self.config.setValue("endereco", endereco)
        self.accept()

    def valores(self):
        return self.nome.text().strip(), self.endereco()


class FormularioProjeto(QMainWindow):
    """Tela_criar.ui"""

    def __init__(self, controlador, ao_criar=None):
        super().__init__()
        carregar_ui("Tela_criar.ui", self)
        self.controlador = controlador
        self.setWindowTitle("Criar projeto")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.menuBar().hide()
        # textos corrigidos aqui (no Designer ainda têm erros de digitação)
        self.label.setText("Digite o nome do projeto:")
        self.label_2.setText("Digite a descrição do projeto:")
        self.label_3.setText("Digite o nome do responsável pelo projeto:")
        self.label_4.setText("Digite o nome da pessoa envolvida no projeto:")
        self.label_7.setText("Pessoas envolvidas no projeto")
        self.pushButton.setText("Adicionar")
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Nome", "Cargo"])
        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pushButton.clicked.connect(self.adicionar_pessoa)
        self.pushButton_2.clicked.connect(self.remover_pessoa)
        self.pushButton_3.clicked.connect(self.concluir)
        self.pushButton_4.clicked.connect(self.close)

    def adicionar_pessoa(self):
        nome, cargo = self.lineEdit_4.text().strip(), self.lineEdit_5.text().strip()
        if not nome:
            return
        linha = self.tableWidget.rowCount()
        self.tableWidget.insertRow(linha)
        self.tableWidget.setItem(linha, 0, QTableWidgetItem(nome))
        self.tableWidget.setItem(linha, 1, QTableWidgetItem(cargo))
        self.lineEdit_4.clear()
        self.lineEdit_5.clear()

    def remover_pessoa(self):
        linha = self.tableWidget.currentRow()
        if linha >= 0:
            self.tableWidget.removeRow(linha)

    def concluir(self):
        pessoas = []
        for i in range(self.tableWidget.rowCount()):
            pessoas.append({"nome": self.tableWidget.item(i, 0).text(),
                            "cargo": self.tableWidget.item(i, 1).text()})
        dados = {"nome": self.lineEdit.text(), "descricao": self.lineEdit_2.text(),
                 "responsavel": self.lineEdit_3.text(), "pessoas": pessoas}
        self.controlador.criar_projeto(dados, ao_sucesso=lambda _: self.close())


class JanelaPrincipal(QMainWindow):
    """Tela_principal.ui"""

    def __init__(self, controlador):
        super().__init__()
        carregar_ui("Tela_principal.ui", self)
        self.controlador = controlador
        self.arvore = None
        self.formulario = None
        self.setWindowTitle("Organizador de Projetos")
        self.menuBar().hide()
        self.listView_2.hide()
        self.listView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.modelo = QStandardItemModel(self.listView)
        self.listView.setModel(self.modelo)
        self.botao_abrir = QPushButton("Abrir Projeto", self.centralwidget)
        self.botao_abrir.setGeometry(0, 180, 191, 91)

        self.barra = BarraDeStatus(self.statusBar(), controlador.usuario)
        self.barra.mostrar(controlador.estado)

        self.pushButton.clicked.connect(self.criar)
        self.pushButton_2.clicked.connect(self.excluir)
        self.botao_abrir.clicked.connect(self.abrir)
        self.listView.doubleClicked.connect(lambda _: self.abrir())

        controlador.estado_mudou.connect(self.barra.mostrar)
        controlador.projetos_mudaram.connect(self.exibir_projetos)
        controlador.novidade.connect(self.barra.aviso)
        controlador.aviso.connect(lambda t: QMessageBox.warning(QApplication.activeWindow(), "Conflito", t))
        controlador.erro.connect(lambda t: QMessageBox.warning(QApplication.activeWindow(), "Atenção", t))
        controlador.nao_autorizado.connect(self._nao_autorizado)

    def exibir_projetos(self, projetos):
        selecionado = self._selecionado()
        self.modelo.clear()
        for p in projetos:
            item = QStandardItem(f"{p['nome']}   —   {p['progresso']}% concluído   "
                                 f"(responsável: {p['responsavel'] or '—'})")
            item.setData(p["id"], ID)
            item.setData(p["versao"], TIPO)
            item.setData(p["nome"], STATUS)
            self.modelo.appendRow(item)
            if selecionado and selecionado[0] == p["id"]:
                self.listView.setCurrentIndex(item.index())

    def _selecionado(self):
        indice = self.listView.currentIndex()
        if not indice.isValid():
            return None
        item = self.modelo.itemFromIndex(indice)
        return item.data(ID), item.data(TIPO), item.data(STATUS)

    def criar(self):
        self.formulario = FormularioProjeto(self.controlador)
        self.formulario.show()

    def abrir(self):
        sel = self._selecionado()
        if not sel:
            self.barra.aviso("Selecione um projeto.")
            return
        self.controlador.abrir_projeto(sel[0], ao_sucesso=self._mostrar_arvore)

    def _mostrar_arvore(self, projeto):
        if self.arvore is not None:
            self.arvore.close()
        self.arvore = ArvoreDeItens(self.controlador)
        self.arvore.show()

    def excluir(self):
        sel = self._selecionado()
        if not sel:
            self.barra.aviso("Selecione um projeto.")
            return
        if perguntar(self, "Excluir projeto", f"Excluir o projeto '{sel[2]}'?"):
            self.controlador.excluir_projeto(sel[0], sel[1])

    def _nao_autorizado(self, mensagem):
        self.barra.sem_acesso()
        QMessageBox.warning(self, "Acesso negado", MSG_SEM_ACESSO)

    def closeEvent(self, evento):
        if self.arvore is not None:
            self.arvore.close()
        super().closeEvent(evento)


class ArvoreDeItens(QMainWindow):
    """Tarefas.ui: fases e tarefas em árvore, com progresso e dependências."""
    ROTULO = {"pendente": "pendente", "em_andamento": "em andamento", "concluida": "concluída"}

    def __init__(self, controlador):
        super().__init__()
        carregar_ui("Tarefas.ui", self)
        self.controlador = controlador
        self.id_projeto = controlador.projeto["id"]
        self.menuBar().hide()
        # a lista simples do Designer dá lugar a uma árvore
        self.listView.hide()
        self.arvore = QTreeWidget(self.centralwidget)
        self.arvore.setGeometry(250, 0, 550, 540)
        self.arvore.setColumnCount(5)
        self.arvore.setHeaderLabels(["Item", "Status", "Progresso", "Responsável", "Depende de"])
        self.arvore.setColumnWidth(0, 170)
        self.arvore.setColumnWidth(3, 90)
        self.arvore.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # botões extras (os três primeiros vêm do Designer)
        self.botao_fase = self._botao("Criar Fase", 270)
        self.botao_status = self._botao("Avançar Status", 360)
        self.botao_dep = self._botao("Dependência", 450)
        self.botao_pessoas = self._botao("Pessoas", 0)
        self.botao_editar_fase = self._botao("Editar Fase", 0)
        self.pushButton_2.setText("Editar Tarefa")
        self.pushButton_3.setText("Excluir")
        botoes = [self.pushButton, self.pushButton_2, self.pushButton_3, self.botao_fase,
                  self.botao_editar_fase, self.botao_status, self.botao_dep, self.botao_pessoas]
        for i, botao in enumerate(botoes):
            botao.setGeometry(0, i * 66, 251, 66)
        self.pushButton.clicked.connect(self.criar_tarefa)
        self.pushButton_2.clicked.connect(self.editar_tarefa)
        self.pushButton_3.clicked.connect(self.excluir)
        self.botao_fase.clicked.connect(self.criar_fase)
        self.botao_editar_fase.clicked.connect(self.editar_fase)
        self.botao_status.clicked.connect(self.avancar_status)
        self.botao_dep.clicked.connect(self.criar_dependencia)
        self.botao_pessoas.clicked.connect(self.mostrar_pessoas)
        self.tarefas = {}
        controlador.projeto_mudou.connect(self.exibir)
        controlador.projeto_removido.connect(self._removido)
        self.exibir(controlador.projeto)

    def _botao(self, texto, y):
        botao = QPushButton(texto, self.centralwidget)
        botao.setGeometry(0, y, 251, 91)
        return botao

    # ---------- exibição ----------
    def exibir(self, projeto):
        if not projeto or projeto["id"] != self.id_projeto:
            return
        self.setWindowTitle(f"{projeto['nome']} — {projeto['progresso']}% concluído")
        self.tarefas = {}
        self._coletar(projeto["itens"])
        depende = {}
        for d in projeto["dependencias"]:
            depende.setdefault(d["origem_id"], []).append(self.tarefas.get(d["destino_id"], "?"))
        selecionado = self._id_selecionado()
        self.arvore.clear()
        self._montar(self.arvore.invisibleRootItem(), projeto["itens"], depende)
        self.arvore.expandAll()
        if selecionado:
            it = QTreeWidgetItemIterator(self.arvore)
            while it.value():
                if it.value().data(0, ID) == selecionado:
                    self.arvore.setCurrentItem(it.value())
                it += 1

    def _coletar(self, itens):
        for i in itens:
            if i["tipo"] == "tarefa":
                self.tarefas[i["id"]] = i["nome"]
            else:
                self._coletar(i["itens"])

    def _montar(self, pai, itens, depende):
        for i in itens:
            status = self.ROTULO[i["status"]] if i["tipo"] == "tarefa" else "fase"
            item = QTreeWidgetItem(pai, [i["nome"], status, f"{i['progresso']}%",
                                         i.get("responsavel") or "",
                                         ", ".join(depende.get(i["id"], []))])
            item.setData(0, ID, i["id"])
            item.setData(0, TIPO, i["tipo"])
            item.setData(0, STATUS, i.get("percentual"))
            if i["tipo"] == "fase":
                self._montar(item, i["itens"], depende)

    def _removido(self, projeto_id):
        if projeto_id == self.id_projeto:
            QMessageBox.information(self, "Projeto removido", "Este projeto foi excluído por outro usuário.")
            self.close()

    # ---------- ações ----------
    def _selecionado(self):
        item = self.arvore.currentItem()
        if item is None:
            self.statusBar().showMessage("Selecione um item.", 4000)
        return item

    def _id_selecionado(self):
        item = self.arvore.currentItem()
        return item.data(0, ID) if item else None

    def _pedir_nome(self, titulo, rotulo, padrao=""):
        nome, ok = QInputDialog.getText(self, titulo, rotulo, text=padrao)
        return nome.strip() if ok and nome.strip() else None

    def criar_fase(self):
        nome = self._pedir_nome("Criar fase", "Nome da fase:")
        if nome:
            self.controlador.criar_item("fase", nome)

    def _pedir_responsavel(self, atual=""):
        """Escolhe entre as pessoas do projeto. Devolve None se o usuário cancelar."""
        projeto = self.controlador.projeto
        nomes = [p["nome"] for p in projeto.get("pessoas", [])]
        if projeto.get("responsavel") and projeto["responsavel"] not in nomes:
            nomes.insert(0, projeto["responsavel"])
        if atual and atual not in nomes:
            nomes.append(atual)
        opcoes = ["(ninguém)"] + nomes
        posicao = opcoes.index(atual) if atual in opcoes else 0
        escolha, ok = QInputDialog.getItem(self, "Responsável", "Responsável pela tarefa:",
                                           opcoes, posicao, False)
        if not ok:
            return None
        return "" if escolha == "(ninguém)" else escolha

    def criar_tarefa(self):
        pai_id, sel = None, self.arvore.currentItem()
        if sel is not None:
            if sel.data(0, TIPO) == "fase":
                pai_id = sel.data(0, ID)
            elif sel.parent() is not None:
                pai_id = sel.parent().data(0, ID)
        if pai_id is None:
            self.statusBar().showMessage("Selecione uma fase para criar a tarefa (ou crie uma fase antes).", 6000)
            return
        nome = self._pedir_nome("Criar tarefa", "Nome da tarefa:")
        if not nome:
            return
        responsavel = self._pedir_responsavel()
        if responsavel is None:
            return
        self.controlador.criar_item("tarefa", nome, pai_id, responsavel)

    def mostrar_pessoas(self):
        projeto = self.controlador.projeto
        linhas = [f"Responsável pelo projeto: {projeto.get('responsavel') or '—'}", "", "Pessoas envolvidas:"]
        for p in projeto.get("pessoas", []):
            linhas.append(f"  • {p['nome']} — {p.get('cargo') or 'sem cargo'}")
        if not projeto.get("pessoas"):
            linhas.append("  (nenhuma)")
        QMessageBox.information(self, "Pessoas do projeto", "\n".join(linhas))

    def editar_tarefa(self):
        self._renomear("tarefa")

    def editar_fase(self):
        self._renomear("fase")

    def _renomear(self, tipo):
        sel = self._selecionado()
        if sel is None:
            return
        if sel.data(0, TIPO) != tipo:
            self.statusBar().showMessage(f"Selecione uma {tipo}.", 4000)
            return
        nome = self._pedir_nome(f"Editar {tipo}", "Novo nome:", sel.text(0))
        if not nome:
            return
        if tipo == "tarefa":
            responsavel = self._pedir_responsavel(sel.text(3))
            if responsavel is None:
                return
            self.controlador.renomear_item(sel.data(0, ID), nome, responsavel)
        else:
            self.controlador.renomear_item(sel.data(0, ID), nome)

    def excluir(self):
        sel = self._selecionado()
        if sel is None:
            return
        if perguntar(self, "Excluir", f"Excluir '{sel.text(0)}'?"):
            self.controlador.excluir_item(sel.data(0, ID))

    def avancar_status(self):
        sel = self._selecionado()
        if sel is None:
            return
        if sel.data(0, TIPO) != "tarefa":
            self.statusBar().showMessage("Só tarefas têm status.", 4000)
            return
        atual = sel.data(0, STATUS)          # percentual atual da tarefa
        novo = 0 if atual >= 100 else atual + 10
        self.controlador.mudar_percentual(sel.data(0, ID), novo)

    def criar_dependencia(self):
        sel = self._selecionado()
        if sel is None:
            return
        if sel.data(0, TIPO) != "tarefa":
            self.statusBar().showMessage("Selecione uma tarefa.", 4000)
            return
        origem = sel.data(0, ID)
        outras = {i: nome for i, nome in self.tarefas.items() if i != origem}
        if not outras:
            self.statusBar().showMessage("Não há outra tarefa para escolher.", 4000)
            return
        repetidos = {n for n in outras.values() if list(outras.values()).count(n) > 1}
        opcoes = {}
        for i, nome in outras.items():
            rotulo = nome if nome not in repetidos else f"{nome} ({self._fase_de(i)})"
            opcoes[rotulo] = i
        escolha, ok = QInputDialog.getItem(self, "Dependência", f"'{sel.text(0)}' depende de:",
                                           list(opcoes), 0, False)
        if ok:
            self.controlador.adicionar_dependencia(origem, opcoes[escolha])

    def _fase_de(self, tarefa_id):
        """Nome da fase que contém a tarefa (para diferenciar tarefas com o mesmo nome)."""
        it = QTreeWidgetItemIterator(self.arvore)
        while it.value():
            if it.value().data(0, ID) == tarefa_id:
                pai = it.value().parent()
                return pai.text(0) if pai is not None else "sem fase"
            it += 1
        return "?"