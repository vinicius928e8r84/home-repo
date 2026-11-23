import re

from scripts.freios.contexto import Achado
from scripts.freios.skills import PASTA_DOS_SKILLS, nomes_dos_skills

ID = "orcamento"
TITULO = "O contexto que o agente carrega no começo da sessão cabe no orçamento de tokens"
CONSERTO = (
    "Encurte os arquivos de instrução ou as descrições dos skills: tudo isso entra no contexto de toda "
    "sessão. Subir um teto em scripts/freios/limites.json é decisão do dono."
)
BYTES_POR_TOKEN = 4
CHAVE = re.compile(r"^([A-Za-z][\w-]*):[ \t]*(.*)$")


def tokens(dados):
    return -(-len(dados) // BYTES_POR_TOKEN)


def descricao(texto):
    if not texto.startswith("---\n"):
        return ""
    fim = texto.find("\n---", 4)
    if fim < 0:
        return ""
    partes = {}
    chave_atual = None
    for linha in texto[4:fim].split("\n"):
        chave = CHAVE.match(linha)
        if chave and not linha.startswith(" "):
            chave_atual = chave.group(1)
            partes[chave_atual] = [chave.group(2)]
        elif chave_atual is not None:
            partes[chave_atual].append(linha.strip())
    return _limpar(" ".join(parte for parte in partes.get("description", []) if parte))


def _limpar(valor):
    valor = re.sub(r"^[>|][+-]?\s*", "", valor.strip())
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        valor = valor[1:-1]
    return valor


def _tokens_dos_arquivos(ctx, caminhos):
    total = 0
    for caminho in caminhos:
        entrada = ctx.arquivos.get(caminho)
        dados = ctx.ler(entrada) if entrada else None
        total += tokens(dados) if dados else 0
    return total


def _tokens_das_descricoes(ctx):
    total = 0
    for nome in nomes_dos_skills(ctx):
        texto = ctx.texto(ctx.arquivos[f"{PASTA_DOS_SKILLS}/{nome}/SKILL.md"])
        total += tokens(descricao(texto or "").encode("utf-8"))
    return total


def verificar(ctx):
    config = ctx.limites["orcamento"]
    achados = []
    usados = _tokens_dos_arquivos(ctx, config["arquivos"])
    if usados > config["tokens_dos_arquivos"]:
        lista = ", ".join(config["arquivos"])
        detalhe = f"{lista} somam ~{usados} tokens, acima do teto de {config['tokens_dos_arquivos']}"
        achados.append(Achado(ID, config["arquivos"][0], detalhe))
    usados = _tokens_das_descricoes(ctx)
    if usados > config["tokens_das_descricoes"]:
        detalhe = (
            f"as descrições dos skills somam ~{usados} tokens, acima do teto de {config['tokens_das_descricoes']}"
        )
        achados.append(Achado(ID, PASTA_DOS_SKILLS, detalhe))
    return achados
