import os
import re
import sys
import time

from scripts.freios import saida_utf8
from scripts.freios.github_api import Cliente, ErroDoGitHub

WORKFLOW = "registro-da-pr.yml"
TENTATIVAS = 30
PASSO_EM_SEGUNDOS = 10
USO = "uso: GITHUB_TOKEN=… GITHUB_REPOSITORY=<dono/repo> PR=<número> python -m scripts.freios.reexecutar_registro"


def run_do_head(cliente, head):
    caminho = f"actions/workflows/{WORKFLOW}/runs?head_sha={head}&event=pull_request&per_page=1"
    runs = cliente.pedir("GET", caminho)["workflow_runs"]
    return runs[0] if runs else None


def esperar_o_fim(cliente, head, dormir):
    run = run_do_head(cliente, head)
    for _ in range(TENTATIVAS):
        if run is None or run["status"] == "completed":
            return run
        dormir(PASSO_EM_SEGUNDOS)
        run = run_do_head(cliente, head)
    return run


def reexecutar(cliente, pr, dormir):
    head = cliente.pedir("GET", f"pulls/{pr}")["head"]["sha"]
    run = esperar_o_fim(cliente, head, dormir)
    if run is None:
        print(f"nenhum run do check Registro da PR para o head {head}: nada a reexecutar")
        return 0
    if run["status"] != "completed":
        print(f"✗ o run {run['id']} do check Registro da PR não terminou: não reexecutei")
        return 1
    cliente.pedir("POST", f"actions/runs/{run['id']}/rerun")
    print(f"Reexecutando o run {run['id']} do check Registro da PR no head {head}")
    return 0


def main(env):
    if not env.get("GITHUB_REPOSITORY") or not re.fullmatch(r"\d+", env.get("PR", "")):
        print(USO)
        return 2
    try:
        return reexecutar(Cliente(env), env["PR"], time.sleep)
    except ErroDoGitHub as erro:
        print(f"✗ {erro}")
        return 2


if __name__ == "__main__":
    saida_utf8.configurar()
    sys.exit(main(dict(os.environ)))
