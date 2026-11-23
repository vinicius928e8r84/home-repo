import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.freios.contexto import Contexto, Entrada, carregar_json


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


def entradas_do_diretorio(raiz):
    saida = git(raiz, "ls-files", "--others", "--exclude-standard", "-z").decode("utf-8", errors="replace")
    novas = [Entrada(c) for c in filter(None, saida.split("\0")) if (Path(raiz) / c).is_file()]
    return entradas_do_indice(raiz) + novas


def caminhos_do_commit(raiz):
    saida = git(raiz, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return set(filter(None, saida.decode("utf-8", errors="replace").split("\0")))


def ref_existe(raiz, ref):
    resposta = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=raiz, capture_output=True, check=False,
    )
    return resposta.returncode == 0


def commits_entre(raiz, base, cabeca):
    formato = "%H%x09%ae%x09%ce%x09%s%x1f%B"
    saida = git(raiz, "log", "-z", "--no-show-signature", f"--format={formato}", f"{base}..{cabeca}")
    commits = []
    for registro in filter(None, saida.decode("utf-8", errors="replace").split("\0")):
        cabecalho, _, mensagem = registro.partition("\x1f")
        sha, autor, committer, *assunto = cabecalho.split("\t")
        commits.append(Commit(sha, autor, committer, "\t".join(assunto), mensagem))
    return commits


def leitor_do_disco(raiz):
    def ler(entrada):
        if entrada.modo == "120000":
            return git(raiz, "cat-file", "blob", entrada.sha)
        dados = (Path(raiz) / entrada.caminho).read_bytes()
        return dados if b"\0" in dados else dados.replace(b"\r\n", b"\n")
    return ler


def leitor_do_indice(raiz):
    def ler(entrada):
        return git(raiz, "cat-file", "blob", entrada.sha)
    return ler


def montar_contexto(raiz, modo, base):
    universo = entradas_do_indice(raiz)
    if modo == "commit":
        escolhidos = caminhos_do_commit(raiz)
        alvos = [e for e in universo if e.caminho in escolhidos]
        leitor = leitor_do_indice(raiz)
    else:
        universo = entradas_do_diretorio(raiz)
        alvos = universo
        leitor = leitor_do_disco(raiz)
    limites = carregar_json("limites.json")
    excecoes = carregar_json("excecoes.json")
    return Contexto(raiz, universo, alvos, leitor, limites, excecoes, base, modo)
