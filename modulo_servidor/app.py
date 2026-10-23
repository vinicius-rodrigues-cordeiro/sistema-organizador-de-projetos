import os
from flask import Flask, jsonify, request, g

from repositorio import ArmazenamentoJson, RepositorioUsuarios, RepositorioProjetos
from mediador import MediadorColaboracao
from servicos import ServicoProjetos, ServicoDependencias
from rotas import registrar_rotas

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    import socket
    app = criar_app()
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = "127.0.0.1"
    print("Servidor nesta máquina:   http://127.0.0.1:5000")
    print(f"Para outras máquinas:     http://{ip}:5000")
    app.run(host="0.0.0.0", port=5000)