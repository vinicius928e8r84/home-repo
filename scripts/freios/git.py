import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.freios.contexto import Configuracao, Contexto, Entrada, Selecao, carregar_json


@dataclass(frozen=True)
class Commit:
    sha: str
    autor: str
    committer: str
    assunto: str
    mensagem: str


def git(raiz, *args, entrada=None):
    resposta = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=raiz, input=entrada, capture_output=True, check=False,
    )
    if resposta.returncode != 0:
        erro = resposta.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)}: {erro}")
    return resposta.stdout


def raiz_do_repositorio(inicio):
    saida = git(inicio, "rev-parse", "--show-toplevel")
    return Path(saida.decode("utf-8").strip())


def entradas_do_indice(raiz):
    saida = git(raiz, "ls-files", "-s", "-z").decode("utf-8", errors="replace")
    entradas = []
    for registro in filter(None, saida.split("\0")):
        cabecalho, caminho = registro.split("\t", 1)
        modo, sha, _ = cabecalho.split(" ")
        entradas.append(Entrada(caminho, modo, sha))
    return entradas


def caminhos_do_commit(raiz):
    saida = git(raiz, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return set(filter(None, saida.decode("utf-8", errors="replace").split("\0")))


def ref_existe(raiz, ref):
    resposta = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=raiz, capture_output=True, check=False,
    )
    return resposta.returncode == 0


def ponto_de_comparacao(raiz, base):
    if not base or not ref_existe(raiz, base):
        return None
    resposta = subprocess.run(["git", "merge-base", "HEAD", base], cwd=raiz, capture_output=True, check=False)
    if resposta.returncode == 0 and resposta.stdout.strip():
        return resposta.stdout.decode("utf-8").strip()
    return base


def entradas_da_ref(raiz, ref):
    saida = git(raiz, "ls-tree", "-r", "-z", ref).decode("utf-8", errors="replace")
    entradas = []
    for registro in filter(None, saida.split(chr(0))):
        cabecalho, caminho = registro.split(chr(9), 1)
        modo, tipo, sha = cabecalho.split(" ")
        if tipo == "blob":
            entradas.append(Entrada(caminho, modo, sha))
    return entradas


def commits_entre(raiz, base, cabeca):
    formato = "%H%x09%ae%x09%ce%x09%s%x1f%B"
    saida = git(raiz, "log", "-z", "--no-show-signature", f"--format={formato}", f"{base}..{cabeca}")
    commits = []
    for registro in filter(None, saida.decode("utf-8", errors="replace").split("\0")):
        cabecalho, _, mensagem = registro.partition("\x1f")
        sha, autor, committer, *assunto = cabecalho.split("\t")
        commits.append(Commit(sha, autor, committer, "\t".join(assunto), mensagem))
    return commits


def leitor_do_indice(raiz):
    def ler(entrada):
        return git(raiz, "cat-file", "blob", entrada.sha)
    return ler


def montar_contexto(raiz, modo, base):
    universo = entradas_do_indice(raiz)
    alvos = universo
    if modo == "commit":
        escolhidos = caminhos_do_commit(raiz)
        alvos = [e for e in universo if e.caminho in escolhidos]
    configuracao = Configuracao(carregar_json("limites.json"), carregar_json("excecoes.json"), base, modo)
    return Contexto(raiz, Selecao(universo, alvos), leitor_do_indice(raiz), configuracao)
