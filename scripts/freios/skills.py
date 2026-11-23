import posixpath
import re
import subprocess
import sys

from scripts.freios.contexto import Achado

ID = "skills"
TITULO = "Todo skill passa no validate.py e tem o seu link em .claude/skills (e o contrário)"
CONSERTO = (
    "Conserte o que o validate.py aponta. Cada pasta de .agents/skills/<nome> com SKILL.md tem um link "
    "simbólico .claude/skills/<nome> para ../../.agents/skills/<nome>, e cada link de .claude/skills "
    "aponta para um skill que existe."
)
PASTA_DOS_SKILLS = ".agents/skills"
PASTA_DOS_LINKS = ".claude/skills"
VALIDADOR = ".agents/skills/writing-for-agents/scripts/validate.py"
CABECALHO_DO_VALIDADOR = re.compile(r"^(?P<pasta>\S.*): (?P<estado>ok|FAIL)$")
ERRO_DO_VALIDADOR = re.compile(r"^\s+error: (?P<erro>.*)$")


def nomes_dos_skills(ctx):
    nomes = set()
    for caminho in ctx.arquivos:
        partes = caminho.split("/")
        if caminho.startswith(PASTA_DOS_SKILLS + "/") and len(partes) == 4 and partes[3] == "SKILL.md":
            nomes.add(partes[2])
    return nomes


def _achados_dos_links(ctx, nomes):
    achados = []
    links = {c: a for c, a in ctx.links.items() if posixpath.dirname(c) == PASTA_DOS_LINKS}
    for nome in sorted(nomes):
        caminho = f"{PASTA_DOS_LINKS}/{nome}"
        if caminho not in links:
            achados.append(Achado(ID, caminho, f"falta o link do skill {nome} em {PASTA_DOS_LINKS}"))
    for caminho, alvo in sorted(links.items()):
        achados += _achados_do_link(caminho, alvo, nomes)
    for caminho in sorted(ctx.arquivos):
        if caminho.startswith(PASTA_DOS_LINKS + "/"):
            achados.append(Achado(ID, caminho, f"{PASTA_DOS_LINKS} só tem links para {PASTA_DOS_SKILLS}"))
    return achados


def _achados_do_link(caminho, alvo, nomes):
    nome = posixpath.basename(caminho)
    destino = posixpath.normpath(posixpath.join(PASTA_DOS_LINKS, alvo))
    esperado = f"{PASTA_DOS_SKILLS}/{nome}"
    if destino != esperado:
        return [Achado(ID, caminho, f"aponta para {alvo}, e deveria apontar para ../../{esperado}")]
    if nome not in nomes:
        return [Achado(ID, caminho, f"aponta para um skill que não existe: {esperado}/SKILL.md")]
    return []


def _achados_do_validador(ctx, nomes):
    if VALIDADOR not in ctx.arquivos:
        return [Achado(ID, VALIDADOR, "o validate.py do writing-for-agents não está no repositório")]
    pastas = [f"{PASTA_DOS_SKILLS}/{nome}" for nome in sorted(nomes)]
    comando = [sys.executable, "-X", "utf8", "-I", VALIDADOR, *pastas]
    resposta = subprocess.run(comando, cwd=ctx.raiz, capture_output=True, check=False)
    saida = resposta.stdout.decode("utf-8", errors="replace")
    achados = _erros_do_validador(saida)
    if resposta.returncode != 0 and not achados:
        erro = resposta.stderr.decode("utf-8", errors="replace").strip().splitlines()
        achados.append(Achado(ID, VALIDADOR, erro[-1] if erro else "falhou sem mensagem"))
    return achados


def _erros_do_validador(saida):
    achados = []
    pasta = ""
    for linha in saida.splitlines():
        cabecalho = CABECALHO_DO_VALIDADOR.match(linha)
        erro = ERRO_DO_VALIDADOR.match(linha)
        if cabecalho:
            pasta = cabecalho.group("pasta")
        elif erro:
            achados.append(Achado(ID, f"{pasta}/SKILL.md", erro.group("erro")))
    return achados


def verificar(ctx):
    nomes = nomes_dos_skills(ctx)
    achados = _achados_dos_links(ctx, nomes)
    if nomes and ctx.raiz is not None:
        achados += _achados_do_validador(ctx, nomes)
    return achados
