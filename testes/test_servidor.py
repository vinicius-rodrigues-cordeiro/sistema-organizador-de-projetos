import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modulo_servidor"))

from app import criar_app


class TestBase(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        with open(os.path.join(self.pasta.name, "usuarios.json"), "w", encoding="utf-8") as f:
            json.dump({"usuarios": ["Vinicius", "Colega"]}, f)
        self.abrir()
        self.a = {"X-Usuario": "Vinicius"}
        self.b = {"X-Usuario": "Colega"}

    def abrir(self):
        """(Re)cria o app sobre os mesmos arquivos, como reiniciar o servidor."""
        self.cliente = criar_app(self.pasta.name).test_client()

    def tearDown(self):
        self.pasta.cleanup()

    def criar(self, **extra):
        r = self.cliente.post("/projetos", json={"nome": "Projeto X", **extra}, headers=self.a)
        self.assertEqual(r.status_code, 201)
        return r.get_json()

    def tarefas(self, projeto):
        achadas = []
        def descer(itens):
            for i in itens:
                if i["tipo"] == "tarefa":
                    achadas.append(i)
                else:
                    descer(i["itens"])
        descer(projeto["itens"])
        return achadas

    def status(self, item_id, status, versao, quem=None):
        return self.cliente.put(f"/itens/{item_id}/status",
                                json={"status": status, "versao": versao}, headers=quem or self.a)

    def dep(self, projeto, origem, destino):
        return self.cliente.post("/dependencias", headers=self.a, json={
            "projeto_id": projeto["id"], "origem_id": origem, "destino_id": destino,
            "versao": projeto["versao"]})


class TestAcesso(TestBase):
    def test_saude_nao_exige_usuario(self):
        self.assertEqual(self.cliente.get("/saude").status_code, 200)

    def test_sem_usuario_retorna_401(self):
        self.assertEqual(self.cliente.get("/projetos").status_code, 401)

    def test_usuario_desconhecido_retorna_401(self):
        r = self.cliente.get("/projetos", headers={"X-Usuario": "Intruso"})
        self.assertEqual(r.status_code, 401)


class TestProjetos(TestBase):
    def test_ca01_so_com_nome(self):
        p = self.criar()
        self.assertEqual(p["nome"], "Projeto X")
        self.assertEqual(p["itens"], [])
        self.assertGreater(p["versao"], 0)

    def test_ca02_todos_os_campos(self):
        p = self.criar(descricao="desc", responsavel="Vinicius",
                       pessoas=[{"nome": "Ana", "cargo": "Dev"}],
                       fases=[{"nome": "Fase 1", "tarefas": ["T1", "T2"]}])
        self.assertEqual(p["descricao"], "desc")
        self.assertEqual(p["pessoas"][0]["cargo"], "Dev")
        self.assertEqual(len(p["itens"][0]["itens"]), 2)

    def test_ca03_sem_nome_nao_grava(self):
        for corpo in ({}, {"nome": "   "}, {"nome": 5}):
            r = self.cliente.post("/projetos", json=corpo, headers=self.a)
            self.assertEqual(r.status_code, 422)
        self.assertEqual(self.cliente.get("/projetos", headers=self.a).get_json(), [])

    def test_json_malformado_retorna_400(self):
        r = self.cliente.post("/projetos", data="{quebrado", content_type="application/json", headers=self.a)
        self.assertEqual(r.status_code, 400)

    def test_projeto_inexistente_404(self):
        self.assertEqual(self.cliente.get("/projetos/nao-existe", headers=self.a).status_code, 404)

    def test_excluir_projeto(self):
        p = self.criar()
        r = self.cliente.delete(f"/projetos/{p['id']}", json={"versao": p["versao"]}, headers=self.a)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.cliente.get("/projetos", headers=self.a).get_json(), [])


class TestHierarquiaEProgresso(TestBase):
    def test_ca04_hierarquia(self):
        p = self.criar()
        r = self.cliente.post(f"/projetos/{p['id']}/itens", headers=self.a,
                              json={"tipo": "fase", "nome": "F1", "versao": p["versao"]})
        p = r.get_json()
        fase = p["itens"][0]
        r = self.cliente.post(f"/projetos/{p['id']}/itens", headers=self.a,
                              json={"tipo": "tarefa", "nome": "T1", "pai_id": fase["id"], "versao": p["versao"]})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["itens"][0]["itens"][0]["nome"], "T1")

    def test_item_invalido_422(self):
        p = self.criar()
        r = self.cliente.post(f"/projetos/{p['id']}/itens", headers=self.a,
                              json={"tipo": "banana", "nome": "x", "versao": p["versao"]})
        self.assertEqual(r.status_code, 422)

    def test_tarefa_sem_fase_422(self):
        p = self.criar()
        r = self.cliente.post(f"/projetos/{p['id']}/itens", headers=self.a,
                              json={"tipo": "tarefa", "nome": "solta", "versao": p["versao"]})
        self.assertEqual(r.status_code, 422)
        self.assertIn("fase", r.get_json()["erro"])
        atual = self.cliente.get(f"/projetos/{p['id']}", headers=self.a).get_json()
        self.assertEqual(atual["itens"], [])              # nada foi gravado
        self.assertEqual(atual["versao"], p["versao"])

    def test_ca07_progresso_recalculado(self):
        p = self.criar(fases=[{"nome": "F1", "tarefas": ["A", "B"]}])
        a, b = self.tarefas(p)
        self.assertEqual(p["progresso"], 0)
        p = self.status(a["id"], "concluida", p["versao"]).get_json()
        self.assertEqual(p["progresso"], 50)
        self.assertEqual(p["itens"][0]["progresso"], 50)
        p = self.status(b["id"], "concluida", p["versao"]).get_json()
        self.assertEqual(p["progresso"], 100)

    def percentual(self, item_id, valor, versao):
        return self.cliente.put(f"/itens/{item_id}/status",
                                json={"percentual": valor, "versao": versao}, headers=self.a)

    def test_percentual_de_10_em_10(self):
        p = self.criar(fases=[{"nome": "F1", "tarefas": ["A", "B"]}])
        a, b = self.tarefas(p)
        p = self.percentual(a["id"], 10, p["versao"]).get_json()
        self.assertEqual(self.tarefas(p)[0]["status"], "em_andamento")
        self.assertEqual(p["progresso"], 5)           # média de 10% e 0%
        p = self.percentual(a["id"], 100, p["versao"]).get_json()
        self.assertEqual(self.tarefas(p)[0]["status"], "concluida")
        self.assertEqual(p["progresso"], 50)
        p = self.percentual(b["id"], 50, p["versao"]).get_json()
        self.assertEqual(p["progresso"], 75)          # média de 100% e 50%
        self.assertEqual(p["itens"][0]["progresso"], 75)
        p = self.percentual(a["id"], 0, p["versao"]).get_json()
        self.assertEqual(self.tarefas(p)[0]["status"], "pendente")

    def test_percentual_invalido_422(self):
        p = self.criar(fases=[{"nome": "F1", "tarefas": ["A"]}])
        a = self.tarefas(p)[0]
        for valor in (15, 110, -10, "50", True):
            self.assertEqual(self.percentual(a["id"], valor, p["versao"]).status_code, 422)

    def test_status_invalido_422(self):
        p = self.criar(fases=[{"nome": "F1", "tarefas": ["A"]}])
        a = self.tarefas(p)[0]
        self.assertEqual(self.status(a["id"], "feito", p["versao"]).status_code, 422)


class TestDependencias(TestBase):
    def setUp(self):
        super().setUp()
        self.p = self.criar(fases=[{"nome": "F1", "tarefas": ["A", "B", "C"]}])
        self.A, self.B, self.C = [t["id"] for t in self.tarefas(self.p)]

    def test_ca05_dependencia_valida(self):
        r = self.dep(self.p, self.B, self.A)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.get_json()["dependencias"]), 1)

    def test_ca06_invalidas(self):
        self.assertEqual(self.dep(self.p, self.A, self.A).status_code, 422)          # a própria tarefa
        self.assertEqual(self.dep(self.p, self.A, "fantasma").status_code, 422)      # inexistente
        p = self.dep(self.p, self.B, self.A).get_json()
        p = self.dep(p, self.C, self.B).get_json()
        self.assertEqual(self.dep(p, self.A, self.C).status_code, 422)               # ciclo A->C->B->A
        self.assertEqual(self.cliente.get(f"/projetos/{p['id']}", headers=self.a).get_json()["versao"], p["versao"])

    def test_remover_dependencia(self):
        p = self.dep(self.p, self.B, self.A).get_json()
        dep_id = p["dependencias"][0]["id"]
        r = self.cliente.delete(f"/dependencias/{dep_id}", json={"versao": p["versao"]}, headers=self.a)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["dependencias"], [])

    def test_excluir_tarefa_remove_suas_dependencias(self):
        p = self.dep(self.p, self.B, self.A).get_json()
        r = self.cliente.delete(f"/itens/{self.A}", json={"versao": p["versao"]}, headers=self.a)
        self.assertEqual(r.get_json()["dependencias"], [])


class TestColaboracao(TestBase):
    def test_ca08_persistencia(self):
        p = self.criar()
        self.abrir()  # "reinicia" o servidor
        lista = self.cliente.get("/projetos", headers=self.a).get_json()
        self.assertEqual(lista[0]["id"], p["id"])

    def test_ca09_atualizacao_visivel_para_outro_usuario(self):
        p = self.criar()
        r = self.cliente.get("/atualizacoes?desde=0", headers=self.b).get_json()
        self.assertEqual(r["eventos"][0]["autor"], "Vinicius")
        self.assertEqual(r["versao"], p["versao"])
        # sem novidades depois da versão atual
        r2 = self.cliente.get(f"/atualizacoes?desde={r['versao']}", headers=self.b).get_json()
        self.assertEqual(r2["eventos"], [])

    def test_ca10_conflito_de_versao(self):
        p = self.criar()
        ok = self.cliente.put(f"/projetos/{p['id']}", json={"nome": "Do Vinicius", "versao": p["versao"]},
                              headers=self.a)
        self.assertEqual(ok.status_code, 200)
        r = self.cliente.put(f"/projetos/{p['id']}", json={"nome": "Do Colega", "versao": p["versao"]},
                             headers=self.b)
        self.assertEqual(r.status_code, 409)
        self.assertIn("Vinicius", r.get_json()["erro"])
        atual = self.cliente.get(f"/projetos/{p['id']}", headers=self.a).get_json()
        self.assertEqual(atual["nome"], "Do Vinicius")  # a primeira alteração permanece

    def test_sem_versao_422(self):
        p = self.criar()
        r = self.cliente.put(f"/projetos/{p['id']}", json={"nome": "Z"}, headers=self.a)
        self.assertEqual(r.status_code, 422)

    def test_ca11_falha_na_gravacao_preserva_o_arquivo(self):
        p = self.criar()
        with patch("repositorio.ArmazenamentoJson.gravar", side_effect=OSError("disco cheio")):
            r = self.cliente.put(f"/projetos/{p['id']}", json={"nome": "Novo", "versao": p["versao"]},
                                 headers=self.a)
        self.assertEqual(r.status_code, 500)
        self.abrir()
        atual = self.cliente.get(f"/projetos/{p['id']}", headers=self.a).get_json()
        self.assertEqual(atual["nome"], "Projeto X")
        self.assertEqual(atual["versao"], p["versao"])


if __name__ == "__main__":
    unittest.main()