import os
import re

from scripts.freios.contexto import Achado
from scripts.freios.git import commits_entre, ref_existe

ID = "autoria"
TITULO = "Os commits da branch têm o e-mail do dono como autor e nenhum Co-authored-by"
CONSERTO = (
    "Refaça a autoria da branch com o e-mail do dono e tire os Co-authored-by das mensagens: "
    "git config user.email <e-mail do dono>, depois "
    "git rebase --exec 'git commit --amend --no-edit --reset-author' <base> "
    "(e edite a mensagem dos commits com Co-authored-by)."
)
COAUTOR = re.compile(r"^co-authored-by[ \t]*:", re.I | re.M)


def _problemas(commit, donos, aceitos):
    problemas = []
    if commit.autor.lower() not in donos:
        problemas.append(f"autor {commit.autor}")
    if commit.committer.lower() not in donos | aceitos:
        problemas.append(f"committer {commit.committer}")
    if COAUTOR.search(commit.mensagem):
        problemas.append("tem Co-authored-by")
    return problemas


def _sem_base(ctx, base):
    detalhe = f"sem {base} para comparar (git fetch origin main; no CI, fetch-depth 0); commits não conferidos"
    if os.environ.get("CI"):
        return [Achado(ID, "", detalhe)]
    ctx.avisos.append(f"autoria: {detalhe}")
    return []


def verificar(ctx):
    config = ctx.limites["autoria"]
    donos = {e.lower() for e in config["emails_do_dono"]}
    aceitos = {e.lower() for e in config["emails_de_commit_aceitos"]}
    base = ctx.base
    if base is None or not ref_existe(ctx.raiz, base):
        return _sem_base(ctx, base)
    achados = []
    for commit in commits_entre(ctx.raiz, base, "HEAD"):
        problemas = _problemas(commit, donos, aceitos)
        if problemas:
            detalhe = f"{commit.sha[:7]} {commit.assunto}: {', '.join(problemas)}"
            achados.append(Achado(ID, "", detalhe))
    return achados
