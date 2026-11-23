import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.freios import saida_utf8
from scripts.freios.github_api import Cliente, ErroDoGitHub, ler_pr
from scripts.freios.registro_da_pr import (
    ATENCOES,
    FRASE,
    SECAO_DA_PROVA,
    VEREDITO_LIMPO,
    Pr,
    conferir,
    falta_da_prova,
    falta_da_revisao,
)
from scripts.freios.registro_texto import SHA_INTEIRO, fim_da_secao, indice_da_secao, linhas_do_corpo, sem_caixa_nem_acento

PROVA_PARCIAL = "BLOQUEADA-parcial"
RISCOS = {sem_caixa_nem_acento(atencao): atencao for atencao in ATENCOES}
DESCRICAO = (
    "Publica na PR o registro da revisão independente (como uma revisão do tipo comentário, que roda o check "
    "Registro da PR de novo) e a seção Prova real do corpo, sempre com o head lido do GitHub. "
    "Sem --publicar é um ensaio: mostra o texto e o que o check diria depois."
)


def ler_argumentos(argv):
    analisador = argparse.ArgumentParser(prog="python -m scripts.freios.registrar_na_pr", description=DESCRICAO)
    analisador.add_argument("comando", choices=["conferir", "revisao", "prova"])
    analisador.add_argument("--pr", required=True, help="número da PR")
    analisador.add_argument("--head", help="SHA inteiro do commit revisado ou provado")
    analisador.add_argument("--autor", help="quem escreveu a mudança")
    analisador.add_argument("--revisor", help="quem revisou; não é o autor nem quem abriu a PR")
    analisador.add_argument("--risco", help="o risco que o revisor viu: baixa, media ou alta")
    analisador.add_argument("--veredito", default=VEREDITO_LIMPO)
    analisador.add_argument("--cobertura", choices=["total", "parcial"], help="total escreve a frase da prova real")
    analisador.add_argument("--nota", help="arquivo de Markdown que entra depois das linhas do registro")
    analisador.add_argument("--repo", help="<dono/repo>; padrão: GITHUB_REPOSITORY")
    analisador.add_argument("--publicar", action="store_true", help="escreve no GitHub")
    return analisador.parse_args(argv)


def registro_da_revisao(args, head, nota):
    linhas = [
        "Registro de revisão independente",
        "",
        f"Veredito: {args.veredito}",
        f"Head: {head}",
        f"Autor: {args.autor}",
        f"Revisor: {args.revisor}",
        f"Risco: {RISCOS[sem_caixa_nem_acento(args.risco)]}",
    ]
    return "\n".join(linhas + (["", nota.strip()] if nota else []))


def secao_da_prova(head, cobertura, nota):
    frase = FRASE if cobertura == "total" else PROVA_PARCIAL
    linhas = [f"## {SECAO_DA_PROVA}", "", frase, f"Head: {head}"]
    return "\n".join(linhas + (["", nota.strip()] if nota else []))


def corpo_com_a_prova(corpo, secao):
    linhas = re.split(r"\r?\n", corpo or "")
    inicio = indice_da_secao(linhas_do_corpo(corpo), SECAO_DA_PROVA)
    if inicio is None:
        return corpo.rstrip() + "\n\n" + secao + "\n"
    fim = fim_da_secao(linhas_do_corpo(corpo), inicio)
    return "\n".join(linhas[:inicio] + [secao, ""] + linhas[fim:])


def falta_dos_argumentos(args, head_da_pr):
    pedidos = {"revisao": ("head", "autor", "revisor", "risco"), "prova": ("head", "cobertura")}
    faltam = [f"--{nome}" for nome in pedidos.get(args.comando, ()) if not getattr(args, nome)]
    if faltam:
        return f"{args.comando} pede {', '.join(faltam)}"
    if args.risco and sem_caixa_nem_acento(args.risco) not in RISCOS:
        return f"--risco é baixa, media ou alta; veio \"{args.risco}\""
    return falta_do_head_informado(args.head, head_da_pr)


def falta_do_head_informado(informado, head_da_pr):
    if informado is None or informado.strip().lower() == head_da_pr:
        return None
    if not SHA_INTEIRO.match(informado.strip().lower()):
        return f"--head pede o SHA inteiro, de 40 caracteres (git rev-parse HEAD); veio \"{informado}\""
    return (
        f"o head informado é {informado}, e o head da PR agora é {head_da_pr}: "
        "um commit novo muda o head, e o que valia para o anterior não vale; revise ou prove o head novo"
    )


def plano_da_revisao(args, pr, nota):
    comentario = registro_da_revisao(args, pr.head, nota)
    falta = args.veredito == VEREDITO_LIMPO and falta_da_revisao([*pr.registros, comentario], pr.head, pr.autor)
    if falta:
        return {"recusa": f"o check não aceitaria este registro: {falta}"}
    depois = Pr(**{**pr.__dict__, "registros": [*pr.registros, comentario]})
    return {"texto": comentario, "depois": depois, "onde": "O registro da revisão"}


def plano_da_prova(args, pr, nota):
    secao = secao_da_prova(pr.head, args.cobertura, nota)
    corpo = corpo_com_a_prova(pr.corpo, secao)
    falta = args.cobertura == "total" and falta_da_prova(corpo, pr.head)
    if falta:
        return {"recusa": f"o check não aceitaria esta prova: {falta}"}
    depois = Pr(**{**pr.__dict__, "corpo": corpo})
    return {"texto": secao, "corpo": corpo, "depois": depois, "onde": "A seção que entra no corpo"}


def gravar(cliente, args, plano, head):
    if args.comando == "revisao":
        corpo = {"body": plano["texto"], "event": "COMMENT", "commit_id": head}
        cliente.pedir("POST", f"pulls/{args.pr}/reviews", corpo)
    else:
        cliente.pedir("PATCH", f"pulls/{args.pr}", {"body": plano["corpo"]})


def escolher_plano(args, pr, nota):
    erro = falta_dos_argumentos(args, pr.head)
    if erro:
        return {"recusa": erro}
    fazer = plano_da_revisao if args.comando == "revisao" else plano_da_prova
    return fazer(args, pr, nota)


def mostrar(args, plano):
    ensaio = "" if args.publicar else " (ensaio: nada foi publicado; repita com --publicar)"
    print(f"{plano['onde']} da PR {args.pr}{ensaio}:\n")
    print(re.sub(r"(?m)^", "    ", plano["texto"]) + "\n")


def executar(cliente, args, nota):
    pr = Pr(repositorio=cliente.repositorio, **ler_pr(cliente, args.pr))
    if args.comando == "conferir":
        plano = {"depois": pr}
    else:
        plano = escolher_plano(args, pr, nota)
    if "recusa" in plano:
        print(f"✗ Nada foi publicado na PR {args.pr}: {plano['recusa']}")
        return 1
    if args.comando != "conferir":
        mostrar(args, plano)
    if args.publicar and args.comando != "conferir":
        gravar(cliente, args, plano, pr.head)
        print("Publicado; o GitHub roda o check Registro da PR de novo.")
    ok, mensagem = conferir(plano["depois"])
    print(mensagem)
    return 0 if ok else 1


def repositorio_do_origin():
    feito = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=False)
    achado = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", feito.stdout.strip())
    return achado.group(1) if achado else None


def main(argv, env):
    args = ler_argumentos(argv)
    repo = args.repo or env.get("GITHUB_REPOSITORY") or repositorio_do_origin()
    if not repo:
        print("não sei qual é o repositório: passe --repo <dono/repo> ou defina GITHUB_REPOSITORY")
        return 2
    try:
        nota = Path(args.nota).read_text(encoding="utf-8") if args.nota else ""
        return executar(Cliente({**env, "GITHUB_REPOSITORY": repo}), args, nota)
    except (ErroDoGitHub, OSError) as erro:
        print(f"✗ {erro}")
        return 2


if __name__ == "__main__":
    saida_utf8.configurar()
    sys.exit(main(sys.argv[1:], dict(os.environ)))
