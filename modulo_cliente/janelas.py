"""Interface PyQt6. As telas vêm da pasta Ui/ (Qt Designer); aqui só ligamos os botões
e ajustamos o que o Designer não cobre (árvore, textos, botões extras)."""
import os

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFormLayout,
                             QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                             QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator)

from controlador import EstadoConexao

PASTA_UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ui")
ID, TIPO, STATUS = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1, Qt.ItemDataRole.UserRole + 2


def carregar_ui(nome, janela):
    uic.loadUi(os.path.join(PASTA_UI, nome), janela)


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


class DialogoLogin(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Organizador de Projetos")
        self.nome = QLineEdit()
        self.endereco = QLineEdit("127.0.0.1:5000")
        form = QFormLayout(self)
        form.addRow("Seu nome:", self.nome)
        form.addRow("Endereço do servidor:", self.endereco)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self._validar)
        botoes.rejected.connect(self.reject)
        form.addRow(botoes)

    def _validar(self):
        if self.nome.text().strip() and self.endereco.text().strip():
            self.accept()

    def valores(self):
        return self.nome.text().strip(), self.endereco.text().strip()


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
        resposta = QMessageBox.question(self, "Excluir projeto", f"Excluir o projeto '{sel[2]}'?")
        if resposta == QMessageBox.StandardButton.Yes:
            self.controlador.excluir_projeto(sel[0], sel[1])

    def _nao_autorizado(self, mensagem):
        QMessageBox.critical(self, "Acesso negado",
                             f"{mensagem}\nConfira se o nome está em dados/usuarios.json.")
        QApplication.quit()

    def closeEvent(self, evento):
        if self.arvore is not None:
            self.arvore.close()
        super().closeEvent(evento)


class ArvoreDeItens(QMainWindow):
    """Tarefas.ui: fases e tarefas em árvore, com progresso e dependências."""
    PROXIMO = {"pendente": "em_andamento", "em_andamento": "concluida", "concluida": "pendente"}
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
        self.arvore.setColumnCount(4)
        self.arvore.setHeaderLabels(["Item", "Status", "Progresso", "Depende de"])
        self.arvore.setColumnWidth(0, 220)
        self.arvore.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # botões extras (os três primeiros vêm do Designer)
        self.botao_fase = self._botao("Criar Fase", 270)
        self.botao_status = self._botao("Avançar Status", 360)
        self.botao_dep = self._botao("Dependência", 450)
        self.botao_editar_fase = self._botao("Editar Fase", 0)
        self.pushButton_2.setText("Editar Tarefa")
        self.pushButton_3.setText("Excluir")
        botoes = [self.pushButton, self.pushButton_2, self.pushButton_3, self.botao_fase,
                  self.botao_editar_fase, self.botao_status, self.botao_dep]
        for i, botao in enumerate(botoes):
            botao.setGeometry(0, i * 76, 251, 76)
        self.pushButton.clicked.connect(self.criar_tarefa)
        self.pushButton_2.clicked.connect(self.editar_tarefa)
        self.pushButton_3.clicked.connect(self.excluir)
        self.botao_fase.clicked.connect(self.criar_fase)
        self.botao_editar_fase.clicked.connect(self.editar_fase)
        self.botao_status.clicked.connect(self.avancar_status)
        self.botao_dep.clicked.connect(self.criar_dependencia)
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
                                         ", ".join(depende.get(i["id"], []))])
            item.setData(0, ID, i["id"])
            item.setData(0, TIPO, i["tipo"])
            item.setData(0, STATUS, i.get("status"))
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

    def criar_tarefa(self):
        nome = self._pedir_nome("Criar tarefa", "Nome da tarefa:")
        if not nome:
            return
        pai_id, sel = None, self.arvore.currentItem()
        if sel is not None:
            if sel.data(0, TIPO) == "fase":
                pai_id = sel.data(0, ID)
            elif sel.parent() is not None:
                pai_id = sel.parent().data(0, ID)
        self.controlador.criar_item("tarefa", nome, pai_id)

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
        if nome:
            self.controlador.renomear_item(sel.data(0, ID), nome)

    def excluir(self):
        sel = self._selecionado()
        if sel is None:
            return
        resposta = QMessageBox.question(self, "Excluir", f"Excluir '{sel.text(0)}'?")
        if resposta == QMessageBox.StandardButton.Yes:
            self.controlador.excluir_item(sel.data(0, ID))

    def avancar_status(self):
        sel = self._selecionado()
        if sel is None:
            return
        if sel.data(0, TIPO) != "tarefa":
            self.statusBar().showMessage("Só tarefas têm status.", 4000)
            return
        self.controlador.mudar_status(sel.data(0, ID), self.PROXIMO[sel.data(0, STATUS)])

    def criar_dependencia(self):
        sel = self._selecionado()
        if sel is None:
            return
        if sel.data(0, TIPO) != "tarefa":
            self.statusBar().showMessage("Selecione uma tarefa.", 4000)
            return
        origem = sel.data(0, ID)
        opcoes = {f"{nome}  [{i}]": i for i, nome in self.tarefas.items()}
        escolha, ok = QInputDialog.getItem(self, "Dependência", f"'{sel.text(0)}' depende de:",
                                           list(opcoes), 0, False)
        if ok:
            self.controlador.adicionar_dependencia(origem, opcoes[escolha])