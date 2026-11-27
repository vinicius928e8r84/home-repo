import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
USO = """Põe os freios do home-repo num repositório do dono e liga a proteção dele no GitHub.

  instalar.py <dono/repo>                 instala ou atualiza num repo que já existe (abre uma PR)
  instalar.py --novo <nome> [--privado]   cria o repo pelo gh repo create e já o entrega com os freios na main
  --simular                               mostra o que faria, sem criar, empurrar nem mudar nada no GitHub

Copia scripts/freios, os ganchos (.githooks), os workflows Freios e Registro da PR e o modelo de PR.
limites.json, excecoes.json, ruff.toml e o modelo de PR são do repo: só nascem quando faltam (em limites.json, uma chave
nova do home-repo entra sem mexer nas que o repo já tem). Um arquivo do repo que não é nenhuma versão do home-repo é
próprio dele e fica como está. Depois liga o secret scanning e o push protection e protege a main exigindo os checks dos
freios que os workflows do repo rodam, valendo também para admin, sem force push e sem apagar a branch. Num repo que já
existe, quando a PR muda um workflow, a proteção da main espera a PR entrar: rode de novo depois de mesclar."""
COPIADOS = [
    "scripts/__init__.py",
    "scripts/freios/",
    ".githooks/",
    ".github/workflows/freios.yml",
    ".github/workflows/registro-da-pr.yml",
    ".github/workflows/reexecutar-registro-da-pr.yml",
]
FORA = {"scripts/freios/instalar.py", "scripts/freios/test_instalar.py"}
DO_REPOSITORIO = {
    "scripts/freios/limites.json",
    "scripts/freios/excecoes.json",
    "scripts/freios/ruff.toml",
    ".github/PULL_REQUEST_TEMPLATE.md",
}
IGNORADOS = ["__pycache__/", "*.pyc", ".env", "node_modules/"]
CHECKS = ["Freios", "Registro da PR", "Auditoria de dependências"]
APP_DO_ACTIONS = 15368
PREFIXO_DA_BRANCH = "freios/instalar-"
URL_DE_ISSUE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/issues/")


class Falha(Exception):
    pass


def rodar(comando, cwd=None, entrada=None):
    feito = subprocess.run(comando, cwd=cwd, input=entrada, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", check=False)
    if feito.returncode != 0:
        raise Falha(f"{' '.join(comando)} falhou: {(feito.stderr or feito.stdout).strip()}")
    return feito.stdout


def arquivos_do_home(rodar_=rodar):
    listados = rodar_(["git", "ls-files", "--", *COPIADOS, ".github/PULL_REQUEST_TEMPLATE.md"], cwd=RAIZ).split("\n")
    return sorted(c for c in listados if c and c not in FORA)


def blobs_do_home(arquivos, rodar_=rodar):
    blobs = {}
    historia = rodar_(["git", "log", "--all", "--no-renames", "--format=", "--raw", "--no-abbrev", "--", *arquivos], cwd=RAIZ)
    for linha in historia.splitlines():
        info, _, caminho = linha.partition("\t")
        if info.startswith(":") and caminho:
            blobs.setdefault(caminho, set()).update(info.split()[2:4])
    return blobs


def proprios_do_alvo(pasta, arquivos, rodar_=rodar):
    no_alvo = {}
    for linha in rodar_(["git", "ls-tree", "-r", "HEAD"], cwd=pasta).splitlines():
        info, _, caminho = linha.partition("\t")
        no_alvo[caminho] = info.split()[-1]
    conhecidos = blobs_do_home(arquivos, rodar_)
    candidatos = [c for c in arquivos if c in no_alvo and c not in DO_REPOSITORIO]
    return [c for c in candidatos if no_alvo[c] not in conhecidos.get(c, set())]


def checks_do_alvo(pasta):
    workflows = sorted((pasta / ".github/workflows").glob("*.y*ml"))
    textos = "\n".join(w.read_text(encoding="utf-8") for w in workflows)
    return [c for c in CHECKS if re.search(rf"(?m)^\s+name: {re.escape(c)}\s*$", textos)]


def limites_do_alvo():
    limites = json.loads((RAIZ / "scripts/freios/limites.json").read_text(encoding="utf-8"))
    for ferramenta in limites.get("ferramentas", []):
        if ferramenta.get("nome") == "eslint":
            ferramenta["alvo_tudo"] = ["."]
    return limites


def em_json(dados):
    return json.dumps(dados, ensure_ascii=False, indent=2) + "\n"


def conteudo_novo(caminho, slug):
    if caminho == "scripts/freios/limites.json":
        return em_json(limites_do_alvo())
    texto = (RAIZ / caminho).read_text(encoding="utf-8")
    if caminho == ".github/PULL_REQUEST_TEMPLATE.md":
        return URL_DE_ISSUE.sub(f"https://github.com/{slug}/issues/", texto)
    return texto


def juntar_limites(existente, slug):
    atual = json.loads(existente)
    faltam = {chave: valor for chave, valor in limites_do_alvo().items() if chave not in atual}
    return em_json({**atual, **faltam}) if faltam else existente


def juntar_gitignore(existente):
    linhas = existente.splitlines()
    faltam = [linha for linha in IGNORADOS if linha not in linhas]
    if not faltam:
        return existente
    base = existente if not existente or existente.endswith("\n") else existente + "\n"
    return base + "\n".join(faltam) + "\n"


def conteudo_no_alvo(caminho, atual, slug):
    if atual is None:
        return conteudo_novo(caminho, slug)
    if caminho == "scripts/freios/limites.json":
        return juntar_limites(atual, slug)
    if caminho in DO_REPOSITORIO:
        return atual
    return conteudo_novo(caminho, slug)


def ler_se_existe(caminho):
    return caminho.read_text(encoding="utf-8") if caminho.exists() else None


def copiar(pasta, slug, arquivos, proprios=()):
    mudados = []
    for caminho in [c for c in [*arquivos, ".gitignore"] if c not in proprios]:
        destino = pasta / caminho
        atual = ler_se_existe(destino)
        if caminho == ".gitignore":
            novo = juntar_gitignore(atual or "")
        else:
            novo = conteudo_no_alvo(caminho, atual, slug)
        if novo != atual:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(novo, encoding="utf-8", newline="\n")
            mudados.append(caminho)
    for caminho in mudados:
        if caminho.startswith(".githooks/"):
            (pasta / caminho).chmod(0o755)
    return mudados


def protecao_nova(checks):
    return {
        "required_status_checks": {"strict": False, "checks": [{"context": c, "app_id": APP_DO_ACTIONS} for c in checks]},
        "enforce_admins": True,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def checks_juntos(existentes, checks):
    nomes = {c["context"] for c in existentes}
    return existentes + [{"context": c, "app_id": APP_DO_ACTIONS} for c in checks if c not in nomes]


def chamadas_de_protecao(slug, ramo, atual, checks=tuple(CHECKS)):
    seguranca = {s: {"status": "enabled"} for s in ("secret_scanning", "secret_scanning_push_protection")}
    chamadas = [("PATCH", f"repos/{slug}", {"security_and_analysis": seguranca})]
    caminho = f"repos/{slug}/branches/{ramo}/protection"
    if atual is None:
        return chamadas + [("PUT", caminho, protecao_nova(checks))]
    existentes = (atual.get("required_status_checks") or {}).get("checks")
    if existentes is None:
        raise Falha(f"a {ramo} de {slug} já tem proteção, mas sem checks exigidos: ligue-os à mão ({', '.join(checks)})")
    juntos = checks_juntos(existentes, checks)
    if juntos != existentes:
        chamadas.append(("PATCH", f"{caminho}/required_status_checks", {"checks": juntos}))
    if not atual.get("enforce_admins", {}).get("enabled"):
        chamadas.append(("POST", f"{caminho}/enforce_admins", None))
    return chamadas


def protecao_atual(slug, ramo, rodar_=rodar):
    try:
        return json.loads(rodar_(["gh", "api", f"repos/{slug}/branches/{ramo}/protection"]))
    except Falha as erro:
        if "Branch not protected" in str(erro) or "(HTTP 404)" in str(erro):
            return None
        raise


def chamar(chamada, rodar_=rodar):
    metodo, caminho, corpo = chamada
    comando = ["gh", "api", "-X", metodo, caminho]
    if corpo is None:
        return rodar_(comando)
    return rodar_([*comando, "--input", "-"], entrada=json.dumps(corpo))


def descrever(chamada):
    metodo, caminho, corpo = chamada
    return f"{metodo} {caminho}" + (f" {json.dumps(corpo, ensure_ascii=False)}" if corpo is not None else "")


def email_do_dono():
    limites = json.loads((RAIZ / "scripts/freios/limites.json").read_text(encoding="utf-8"))
    return limites["autoria"]["emails_do_dono"][0]


def commitar(pasta, mensagem, rodar_=rodar):
    email = email_do_dono()
    nome = email.split("+", 1)[-1].split("@", 1)[0]
    rodar_(["git", "add", "-A"], cwd=pasta)
    ganchos = [c for c in rodar_(["git", "ls-files", "--", ".githooks/"], cwd=pasta).split("\n") if c]
    if ganchos:
        rodar_(["git", "update-index", "--chmod=+x", "--", *ganchos], cwd=pasta)
    rodar_(["git", "-c", "core.hooksPath=/dev/null", "-c", f"user.name={nome}", "-c", f"user.email={email}",
            "commit", "-q", "-m", mensagem], cwd=pasta)


def corpo_da_pr(plano):
    lista = "\n".join(f"- `{c}`" for c in plano.mudados)
    ficam = "".join(f"- `{c}`\n" for c in plano.proprios)
    if ficam:
        ficam = "\nFicam como estão, por serem próprios deste repo (não são nenhuma versão do home-repo):\n\n" + ficam
    return (
        "## Summary\n\nOs freios do home-repo, postos por `scripts/freios/instalar.py`:\n\n" + lista + "\n" + ficam + "\n"
        "## Merge Danger\n\nAtenção: ALTA\n\nSem issue\n\n"
        "## Prova real\n\nFalta: rode `python scripts/freios/freios.py --tudo` num clone desta branch e cole a saída.\n"
    )


def preparar_pasta(slug, pasta, novo, rodar_=rodar):
    if novo:
        rodar_(["git", "init", "-q", "-b", "main", str(pasta)])
        return "main"
    rodar_(["gh", "repo", "clone", slug, str(pasta), "--", "-q"])
    return rodar_(["gh", "repo", "view", slug, "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]).strip()


def criar_repo(nome, privado, rodar_=rodar):
    rodar_(["gh", "repo", "create", nome, "--private" if privado else "--public"])
    return rodar_(["gh", "repo", "view", nome, "--json", "nameWithOwner", "-q", ".nameWithOwner"]).strip()


def entregar_novo(slug, pasta, rodar_=rodar):
    if not (pasta / "README.md").exists():
        (pasta / "README.md").write_text(f"# {slug.split('/')[-1]}\n", encoding="utf-8", newline="\n")
    commitar(pasta, "Freios do home-repo, postos por scripts/freios/instalar.py", rodar_)
    rodar_(["git", "remote", "add", "origin", f"https://github.com/{slug}.git"], cwd=pasta)
    rodar_(["git", "push", "-q", "origin", "main"], cwd=pasta)
    return f"main de {slug} criada com os freios"


def pr_aberta(slug, rodar_=rodar):
    prs = json.loads(rodar_(["gh", "pr", "list", "--repo", slug, "--state", "open", "--json", "headRefName,url"]) or "[]")
    return next((pr["url"] for pr in prs if pr["headRefName"].startswith(PREFIXO_DA_BRANCH)), None)


def entregar_por_pr(plano, rodar_=rodar):
    slug, pasta, ramo = plano.slug, plano.pasta, plano.ramo
    aberta = pr_aberta(slug, rodar_)
    if aberta:
        return f"já há uma PR dos freios aberta, nada foi empurrado: {aberta}"
    branch = f"{PREFIXO_DA_BRANCH}{date.today().isoformat()}"
    rodar_(["git", "checkout", "-q", "-b", branch], cwd=pasta)
    commitar(pasta, "Freios do home-repo, postos ou atualizados por scripts/freios/instalar.py", rodar_)
    rodar_(["git", "push", "-q", "-u", "origin", branch], cwd=pasta)
    url = rodar_(["gh", "pr", "create", "--repo", slug, "--base", ramo, "--head", branch,
                  "--title", "Freios do home-repo", "--body", corpo_da_pr(plano)], cwd=pasta)
    return f"PR aberta: {url.strip()}"


def ler_argumentos(argv):
    analisador = argparse.ArgumentParser(prog="instalar.py", description=USO,
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
    analisador.add_argument("alvo", nargs="?", help="dono/repo de um repo que já existe")
    analisador.add_argument("--novo", metavar="NOME", help="cria o repo antes de instalar")
    analisador.add_argument("--privado", action="store_true", help="com --novo: cria privado (sem secret scanning)")
    analisador.add_argument("--simular", action="store_true", help="não cria, não empurra, não muda nada no GitHub")
    args = analisador.parse_args(argv)
    if bool(args.alvo) == bool(args.novo):
        analisador.error("diga um repo que já existe (dono/repo) ou --novo <nome>, um dos dois")
    if args.privado and not args.novo:
        analisador.error("--privado só vale com --novo")
    return args


@dataclass
class Plano:
    slug: str
    pasta: Path
    ramo: str
    mudados: list
    proprios: list = field(default_factory=list)
    chamadas: list = field(default_factory=list)
    adiada: bool = False


def planejar(args, slug, pasta, rodar_=rodar):
    novo = bool(args.novo)
    ramo = preparar_pasta(slug, pasta, novo, rodar_)
    arquivos = arquivos_do_home(rodar_)
    proprios = [] if novo else proprios_do_alvo(pasta, arquivos, rodar_)
    plano = Plano(slug, pasta, ramo, copiar(pasta, slug, arquivos, proprios), proprios)
    atual = None if novo else protecao_atual(slug, ramo, rodar_)
    plano.chamadas = chamadas_de_protecao(slug, ramo, atual, checks_do_alvo(pasta))
    if args.privado:
        plano.chamadas = plano.chamadas[1:]
    plano.adiada = not novo and any(c.startswith(".github/workflows/") for c in plano.mudados)
    if plano.adiada:
        plano.chamadas = plano.chamadas[:1]
    return plano


def relatar(plano, saida):
    saida.write(f"{len(plano.mudados)} arquivo(s) a pôr em {plano.slug}:\n" + "".join(f"  {c}\n" for c in plano.mudados))
    if plano.proprios:
        saida.write(f"{len(plano.proprios)} arquivo(s) próprios de {plano.slug} ficam como estão "
                    "(não são nenhuma versão do home-repo):\n" + "".join(f"  {c}\n" for c in plano.proprios))
    if plano.adiada:
        saida.write("A proteção da main espera a PR entrar, porque ela muda os workflows dos checks: "
                    "rode de novo depois de mesclar.\n")


def instalar(args, rodar_=rodar, saida=sys.stdout):
    novo = bool(args.novo)
    slug = args.alvo or args.novo
    if novo and not args.simular:
        slug = criar_repo(args.novo, args.privado, rodar_)
    with tempfile.TemporaryDirectory() as temporaria:
        plano = planejar(args, slug, Path(temporaria) / "repo", rodar_)
        relatar(plano, saida)
        if args.simular:
            saida.write("Simulação: nada foi criado, empurrado nem mudado. Chamadas que faria:\n")
            saida.write("".join(f"  {descrever(c)}\n" for c in plano.chamadas))
            return 0
        if plano.mudados:
            feito = entregar_novo(slug, plano.pasta, rodar_) if novo else entregar_por_pr(plano, rodar_)
            saida.write(feito + "\n")
        for chamada in plano.chamadas:
            chamar(chamada, rodar_)
        if not plano.adiada:
            saida.write(f"Proteção ligada em {slug}: {', '.join(checks_do_alvo(plano.pasta))}, valendo também para admin.\n")
        saida.write("Em cada clone: git config core.hooksPath .githooks\n")
    return 0


def main(argv=None):
    args = ler_argumentos(sys.argv[1:] if argv is None else argv)
    try:
        return instalar(args)
    except Falha as erro:
        sys.stderr.write(f"✗ {erro}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
