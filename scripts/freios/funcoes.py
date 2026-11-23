import ast
from pathlib import Path

from scripts.freios.contexto import Achado

ID = "funcoes"
TITULO = "Nenhuma função Python acima do teto de linhas"
CONSERTO = (
    "Divida a função pelas costuras: cada trecho que faz uma coisa só vira uma função com nome próprio. "
    "Não espreme o código em menos linhas. Uma exceção é um glob com motivo em scripts/freios/excecoes.json."
)
TIPOS_DE_FUNCAO = (ast.FunctionDef, ast.AsyncFunctionDef)


def funcoes_longas(texto, maximo):
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return []
    longas = []
    for no in ast.walk(arvore):
        if isinstance(no, TIPOS_DE_FUNCAO):
            linhas = no.end_lineno - no.lineno + 1
            if linhas > maximo:
                longas.append((no.lineno, no.name, linhas))
    return sorted(longas)


def verificar(ctx):
    config = ctx.limites["funcoes"]
    achados = []
    for entrada in ctx.entradas_com_extensao(set(config["extensoes"])):
        if ctx.excecao(ID, entrada.caminho):
            continue
        texto = ctx.texto(entrada)
        if texto is None or Path(entrada.caminho).suffix.lower() != ".py":
            continue
        for linha, nome, linhas in funcoes_longas(texto, config["linhas_maximas"]):
            detalhe = f"{nome}: {linhas} linhas, acima do teto de {config['linhas_maximas']}"
            achados.append(Achado(ID, entrada.caminho, detalhe, linha))
    return achados
