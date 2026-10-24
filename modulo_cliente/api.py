"""ClienteApi: único ponto que fala com o servidor.

Usa a rede do próprio Qt, de forma assíncrona (a janela não trava).
Toda resposta chega por callback(status, dados); status 0 = sem conexão.
"""
import json

from PyQt6.QtCore import QObject, QUrl, QByteArray
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkRequest

TEMPO_LIMITE_MS = 5000


class ClienteApi(QObject):
    def __init__(self, endereco, usuario):
        super().__init__()
        endereco = endereco.strip().rstrip("/")
        if not endereco.startswith("http"):
            endereco = "http://" + endereco
        self.base = endereco
        self.usuario = usuario
        self.gerente = QNetworkAccessManager(self)
        # fala direto com o servidor, sem passar por proxy da máquina (comum em laboratório)
        self.gerente.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))

    def requisitar(self, metodo, caminho, corpo=None, callback=None):
        pedido = QNetworkRequest(QUrl(self.base + caminho))
        pedido.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        pedido.setRawHeader(b"X-Usuario", self.usuario.encode("utf-8"))
        pedido.setTransferTimeout(TEMPO_LIMITE_MS)
        if metodo == "GET":
            resposta = self.gerente.get(pedido)
        else:
            dados = QByteArray(json.dumps(corpo).encode("utf-8")) if corpo is not None else QByteArray()
            resposta = self.gerente.sendCustomRequest(pedido, metodo.encode(), dados)
        resposta.finished.connect(lambda: self._terminou(resposta, callback))

    def _terminou(self, resposta, callback):
        codigo = resposta.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        status = int(codigo) if codigo is not None else 0
        bruto = bytes(resposta.readAll())
        resposta.deleteLater()
        try:
            dados = json.loads(bruto.decode("utf-8")) if bruto else None
        except ValueError:
            dados = None
        if callback:
            callback(status, dados)