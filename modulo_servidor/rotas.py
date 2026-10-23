"""Rotas da API (contrato do documento v0.3). Só traduz HTTP; a regra fica em servicos.py."""
from flask import jsonify, request, g
from werkzeug.exceptions import BadRequest

from modelo import ErroValidacao, ErroConflito, ErroNaoEncontrado


def registrar_rotas(app, projetos, dependencias, mediador):

    # ---------- erros ----------
    @app.errorhandler(ErroValidacao)
    def _422(e):
        return jsonify({"erro": str(e)}), 422

    @app.errorhandler(ErroConflito)
    def _409(e):
        return jsonify({"erro": str(e)}), 409

    @app.errorhandler(ErroNaoEncontrado)
    def _404(e):
        return jsonify({"erro": str(e)}), 404

    @app.errorhandler(BadRequest)
    def _400(e):
        return jsonify({"erro": "JSON malformado."}), 400

    @app.errorhandler(OSError)
    def _500(e):
        return jsonify({"erro": "Falha ao gravar os dados. Nada foi alterado."}), 500

    # ---------- ajudantes ----------
    def corpo():
        dados = request.get_json(force=True, silent=True)
        if not isinstance(dados, dict):
            raise BadRequest()
        return dados

    def versao_enviada(dados=None):
        v = (dados or {}).get("versao")
        if v is None:
            v = request.args.get("versao")
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            raise ErroValidacao("Versão inválida.")

    def corpo_opcional():
        return request.get_json(force=True, silent=True) or {}

    # ---------- projetos ----------
    @app.get("/projetos")
    def listar_projetos():
        return jsonify(projetos.listar())

    @app.post("/projetos")
    def criar_projeto():
        return jsonify(projetos.criar(g.usuario, corpo())), 201

    @app.get("/projetos/<projeto_id>")
    def obter_projeto(projeto_id):
        return jsonify(projetos.obter(projeto_id))

    @app.put("/projetos/<projeto_id>")
    def editar_projeto(projeto_id):
        dados = corpo()
        return jsonify(projetos.editar(g.usuario, projeto_id, dados, versao_enviada(dados)))

    @app.delete("/projetos/<projeto_id>")
    def excluir_projeto(projeto_id):
        projetos.excluir(g.usuario, projeto_id, versao_enviada(corpo_opcional()))
        return "", 204

    # ---------- itens ----------
    @app.post("/projetos/<projeto_id>/itens")
    def criar_item(projeto_id):
        dados = corpo()
        return jsonify(projetos.criar_item(g.usuario, projeto_id, dados, versao_enviada(dados))), 201

    @app.put("/itens/<item_id>")
    def editar_item(item_id):
        dados = corpo()
        return jsonify(projetos.editar_item(g.usuario, item_id, dados, versao_enviada(dados)))

    @app.delete("/itens/<item_id>")
    def excluir_item(item_id):
        return jsonify(projetos.excluir_item(g.usuario, item_id, versao_enviada(corpo_opcional())))

    @app.put("/itens/<item_id>/status")
    def mudar_status(item_id):
        dados = corpo()
        return jsonify(projetos.mudar_status(g.usuario, item_id, dados, versao_enviada(dados)))

    # ---------- dependências ----------
    @app.post("/dependencias")
    def criar_dependencia():
        dados = corpo()
        return jsonify(dependencias.adicionar(g.usuario, dados, versao_enviada(dados))), 201

    @app.delete("/dependencias/<dependencia_id>")
    def remover_dependencia(dependencia_id):
        return jsonify(dependencias.remover(g.usuario, dependencia_id, versao_enviada(corpo_opcional())))

    # ---------- atualizações (consulta periódica do cliente) ----------
    @app.get("/atualizacoes")
    def atualizacoes():
        return jsonify(mediador.atualizacoes(request.args.get("desde", 0, type=int)))