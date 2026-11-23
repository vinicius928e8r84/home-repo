import json
import shutil
import subprocess
import urllib.error
import urllib.request

QUEM_REGISTRA = ("OWNER", "MEMBER", "COLLABORATOR")
POR_PAGINA = 100


class ErroDoGitHub(Exception):
    pass


def token_do_gh():
    gh = shutil.which("gh")
    if not gh:
        return ""
    feito = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, check=False)
    return feito.stdout.strip() if feito.returncode == 0 else ""


def token_do_ambiente(env):
    return env.get("GITHUB_TOKEN") or env.get("GH_TOKEN") or token_do_gh()


class Cliente:
    def __init__(self, env):
        self.base = env.get("GITHUB_API_URL") or "https://api.github.com"
        self.repositorio = env["GITHUB_REPOSITORY"]
        self.token = token_do_ambiente(env)

    def cabecalhos(self):
        cabecalhos = {"Accept": "application/vnd.github+json", "Content-Type": "application/json"}
        if self.token:
            cabecalhos["Authorization"] = f"Bearer {self.token}"
        return cabecalhos

    def pedir(self, metodo, caminho, corpo=None):
        dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
        url = f"{self.base}/repos/{self.repositorio}/{caminho}"
        pedido = urllib.request.Request(url, data=dados, method=metodo, headers=self.cabecalhos())
        try:
            with urllib.request.urlopen(pedido, timeout=30) as resposta:
                texto = resposta.read().decode("utf-8")
        except urllib.error.HTTPError as erro:
            raise ErroDoGitHub(f"o GitHub respondeu {erro.code} a {caminho}") from erro
        except urllib.error.URLError as erro:
            raise ErroDoGitHub(f"não consegui falar com o GitHub em {caminho}: {erro.reason}") from erro
        return json.loads(texto) if texto else None

    def todas(self, caminho):
        itens = []
        pagina = 1
        while True:
            lote = self.pedir("GET", f"{caminho}?per_page={POR_PAGINA}&page={pagina}")
            itens.extend(lote)
            if len(lote) < POR_PAGINA:
                return itens
            pagina += 1


def corpos_em_ordem(registros):
    aceitos = [r for r in registros if r.get("author_association") in QUEM_REGISTRA]
    aceitos.sort(key=lambda r: r.get("submitted_at") or r.get("created_at") or "")
    return [r.get("body") or "" for r in aceitos]


def caminhos_dos_arquivos(arquivos):
    caminhos = []
    for arquivo in arquivos:
        caminhos.append(arquivo["filename"])
        if arquivo.get("previous_filename"):
            caminhos.append(arquivo["previous_filename"])
    return caminhos


def ler_pr(cliente, numero):
    pr = cliente.pedir("GET", f"pulls/{numero}")
    registros = cliente.todas(f"issues/{numero}/comments") + cliente.todas(f"pulls/{numero}/reviews")
    return {
        "corpo": pr.get("body") or "",
        "registros": corpos_em_ordem(registros),
        "head": pr["head"]["sha"],
        "arquivos": caminhos_dos_arquivos(cliente.todas(f"pulls/{numero}/files")),
        "autor": (pr.get("user") or {}).get("login"),
    }
