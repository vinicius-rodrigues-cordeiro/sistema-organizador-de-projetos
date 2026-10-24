import json
import os
import socket
import threading
from flask import Flask, jsonify, request, g

from repositorio import ArmazenamentoJson, RepositorioUsuarios, RepositorioProjetos
from mediador import MediadorColaboracao
from servicos import ServicoProjetos, ServicoDependencias
from rotas import registrar_rotas

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTA_HTTP = 5000
PORTA_DESCOBERTA = 5001          # UDP: o cliente pergunta "quem é servidor?" e este responde
PERGUNTA = b"ORGANIZADOR?"


def anunciar(porta_http=PORTA_HTTP, porta_descoberta=PORTA_DESCOBERTA):
    """Responde, na rede local, a quem procura o servidor (o cliente lista os que responderem)."""
    try:
        soquete = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        soquete.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        soquete.bind(("", porta_descoberta))
    except OSError:
        return False
    resposta = json.dumps({"servico": "organizador", "nome": socket.gethostname(),
                           "porta": porta_http}).encode("utf-8")

    def ouvir():
        while True:
            try:
                dados, origem = soquete.recvfrom(1024)
                if dados.strip() == PERGUNTA:
                    soquete.sendto(resposta, origem)
            except OSError:          # no Windows, um cliente que sumiu pode gerar erro aqui
                continue
    threading.Thread(target=ouvir, daemon=True).start()
    return True


def ip_da_rede():
    """IP desta máquina na rede local (não envia nada, só descobre qual placa seria usada)."""
    try:
        soquete = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        soquete.connect(("10.255.255.255", 1))
        ip = soquete.getsockname()[0]
        soquete.close()
        return ip
    except OSError:
        return None


def criar_app(pasta_dados=None):
    pasta = pasta_dados or os.path.join(RAIZ, "dados")
    app = Flask(__name__)

    usuarios = RepositorioUsuarios(
        ArmazenamentoJson(os.path.join(pasta, "usuarios.json"), {"usuarios": []}))
    repo_projetos = RepositorioProjetos(
        ArmazenamentoJson(os.path.join(pasta, "projetos.json"), {"versao": 0, "projetos": [], "eventos": []}))

    mediador = MediadorColaboracao(repo_projetos)
    registrar_rotas(app, ServicoProjetos(mediador, repo_projetos),
                    ServicoDependencias(mediador, repo_projetos), mediador)

    @app.before_request
    def identificar_usuario():
        if request.endpoint == "saude":
            return None
        nome = request.headers.get("X-Usuario")
        if not nome or not usuarios.existe(nome):
            return jsonify({"erro": "Usuário não identificado"}), 401
        g.usuario = nome

    @app.get("/saude")
    def saude():
        return jsonify({"status": "ok"}), 200

    return app


if __name__ == "__main__":
    app = criar_app()
    anunciando = anunciar()
    ip = ip_da_rede()
    print(f"Servidor nesta máquina:   http://127.0.0.1:{PORTA_HTTP}")
    if ip:
        print(f"Para outras máquinas:     http://{ip}:{PORTA_HTTP}")
    if anunciando:
        print("Os clientes na mesma rede encontram este servidor sozinhos.")
    else:
        print(f"Aviso: a porta UDP {PORTA_DESCOBERTA} está ocupada; os clientes terão de digitar o endereço.")
    app.run(host="0.0.0.0", port=PORTA_HTTP)