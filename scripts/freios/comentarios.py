import re
from pathlib import Path

from scripts.freios.contexto import Achado
from scripts.freios.lexico import achar_comentarios

ID = "comentarios"
TITULO = "Nenhum comentário nem docstring no código"
CONSERTO = (
    "Apague o comentário: o nome e a estrutura do código devem dizer o que ele faz. "
    "O texto de --help vira uma constante (USO = \"\"\"...\"\"\"). Passam só o #! da linha 1 e a "
    "diretiva com código de regra de uma ferramenta que o repo roda (# noqa: F401, // @ts-expect-error). "
    "Uma exceção é um glob com motivo em scripts/freios/excecoes.json, só por PR revisada pelo dono."
)


def _permitido(linha, trecho, diretivas):
    texto = trecho.strip()
    if linha == 1 and texto.startswith("#!"):
        return True
    return any(d.fullmatch(texto) for d in diretivas)


def _resumo(trecho):
    texto = " ".join(trecho.split())
    return texto if len(texto) <= 60 else texto[:57] + "..."


def verificar(ctx):
    config = ctx.limites["comentarios"]
    diretivas = [re.compile(padrao) for padrao in config["diretivas"]]
    achados = []
    for entrada in ctx.entradas_com_extensao(set(config["extensoes"])):
        if ctx.excecao(ID, entrada.caminho):
            continue
        texto = ctx.texto(entrada)
        if texto is None:
            continue
        extensao = Path(entrada.caminho).suffix.lower()
        for linha, trecho in achar_comentarios(extensao, texto):
            if not _permitido(linha, trecho, diretivas):
                achados.append(Achado(ID, entrada.caminho, _resumo(trecho), linha))
    return achados
