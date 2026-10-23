import json
import os
import threading


class ArmazenamentoJson:
    """Lê e grava um arquivo JSON. Grava em temporário e troca no fim,
    então uma falha no meio nunca estraga o arquivo oficial."""

    def __init__(self, caminho, padrao):
        self.caminho = caminho
        self._trava = threading.Lock()  # uma gravação por vez
        if not os.path.exists(caminho):
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            self.gravar(padrao)

    def ler(self):
        # arquivo corrompido levanta erro, não vira "dados vazios"
        with open(self.caminho, "r", encoding="utf-8") as f:
            return json.load(f)

    def gravar(self, dados):
        with self._trava:
            temporario = self.caminho + ".tmp"
            with open(temporario, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            os.replace(temporario, self.caminho)


class RepositorioUsuarios:
    def __init__(self, armazenamento):
        self.armazenamento = armazenamento

    def existe(self, nome):
        return nome in self.armazenamento.ler()["usuarios"]


class RepositorioProjetos:
    def __init__(self, armazenamento):
        self.armazenamento = armazenamento

    def carregar(self):
        dados = self.armazenamento.ler()
        dados.setdefault("versao", 0)
        dados.setdefault("projetos", [])
        dados.setdefault("eventos", [])
        return dados

    def salvar(self, dados):
        self.armazenamento.gravar(dados)