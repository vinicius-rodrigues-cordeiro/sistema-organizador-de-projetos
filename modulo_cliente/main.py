import sys

from PyQt6.QtWidgets import QApplication, QDialog

from api import ClienteApi
from controlador import ControladorCliente
from janelas import DialogoLogin, JanelaPrincipal


def main():
    app = QApplication(sys.argv)
    login = DialogoLogin()
    if login.exec() != QDialog.DialogCode.Accepted:
        return
    nome, endereco = login.valores()
    controlador = ControladorCliente(ClienteApi(endereco, nome), nome)
    janela = JanelaPrincipal(controlador)
    janela.show()
    controlador.iniciar()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()