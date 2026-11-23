import os
import subprocess
import tempfile
from pathlib import Path

from scripts.freios.contexto import Configuracao, Contexto, Entrada, Selecao, carregar_json


def contexto_de_memoria(arquivos, links=None, raiz=None, **configuracao):
    conteudos = {}
    entradas = []
    for caminho, dados in arquivos.items():
        conteudos[caminho] = dados.encode("utf-8") if isinstance(dados, str) else dados
        entradas.append(Entrada(caminho, "100644", caminho))
    for caminho, alvo in (links or {}).items():
        conteudos[caminho] = alvo.encode("utf-8")
        entradas.append(Entrada(caminho, "120000", caminho))

    def ler(entrada):
        return conteudos[entrada.caminho]

    padrao = {"limites": carregar_json("limites.json"), "excecoes": carregar_json("excecoes.json")}
    padrao.update({chave: valor for chave, valor in configuracao.items() if valor})
    return Contexto(raiz, Selecao(entradas, entradas), ler, Configuracao(**padrao))


class RepositorioTemporario:
    def __init__(self):
        self._herdadas = {n: os.environ.pop(n) for n in list(os.environ) if n.startswith("GIT_") or n == "CI"}
        self._pasta = tempfile.TemporaryDirectory()
        self.raiz = Path(self._pasta.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "dono@example.com")
        self.git("config", "user.name", "Dono")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args, entrada=None):
        resposta = subprocess.run(
            ["git", *args], cwd=self.raiz, input=entrada, capture_output=True, check=True
        )
        return resposta.stdout.decode("utf-8", errors="replace")

    def escrever(self, caminho, conteudo):
        destino = self.raiz / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo)

    def adicionar(self, caminho, conteudo):
        self.escrever(caminho, conteudo)
        self.git("add", caminho)

    def adicionar_link(self, caminho, alvo):
        sha = self.git("hash-object", "-w", "--stdin", entrada=alvo.encode("utf-8")).strip()
        self.git("update-index", "--add", "--cacheinfo", f"120000,{sha},{caminho}")

    def commitar(self, mensagem, email=None, extra=()):
        argumentos = ["commit", "-q", "-m", mensagem, *extra]
        if email:
            argumentos += ["--author", f"Alguem <{email}>"]
        self.git(*argumentos)
        return self.git("rev-parse", "HEAD").strip()

    def limpar(self):
        self._pasta.cleanup()
        os.environ.update(self._herdadas)
