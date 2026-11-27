import ast

from scripts.freios.contexto import Achado

ID = "depuracao"
TITULO = "Nenhum print() esquecido no código Python"
CONSERTO = (
    "Apague o print(): era depuração. Se o arquivo é um script de linha de comando e imprimir é o trabalho dele, "
    "dê a ele o ponto de entrada (if __name__ == \"__main__\":), que o libera. "
    "Um módulo que imprime de propósito sem ter ponto de entrada entra em scripts/freios/excecoes.json, "
    "categoria depuracao, com o motivo, só por PR revisada pelo dono. "
    "Só o print() novo reprova: o que já estava na main fica no teto dela."
)
BOM = "﻿"


def _e_a_guarda(no):
    if not isinstance(no, ast.If) or not isinstance(no.test, ast.Compare):
        return False
    teste = no.test
    pontas = [teste.left, *teste.comparators]
    nomes = [p.id for p in pontas if isinstance(p, ast.Name)]
    textos = [p.value for p in pontas if isinstance(p, ast.Constant)]
    return len(teste.ops) == 1 and isinstance(teste.ops[0], ast.Eq) and nomes == ["__name__"] and textos == ["__main__"]


def _e_print(no):
    return isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "print"


def _linhas_dos_prints(texto, caminho):
    try:
        arvore = ast.parse(texto.lstrip(BOM), caminho)
    except (SyntaxError, ValueError):
        return []
    if any(_e_a_guarda(no) for no in arvore.body):
        return []
    return sorted(no.lineno for no in ast.walk(arvore) if _e_print(no))


def verificar(ctx):
    achados = []
    for entrada in ctx.entradas_com_extensao({".py"}):
        if ctx.excecao(ID, entrada.caminho):
            continue
        texto = ctx.texto(entrada)
        if texto is None:
            continue
        for linha in _linhas_dos_prints(texto, entrada.caminho):
            achados.append(Achado(ID, entrada.caminho, "print() esquecido", linha))
    return achados
