import json
import shutil
import subprocess
from pathlib import Path

from scripts.freios.contexto import Achado, casa

ID = "sintaxe"
TITULO = "Os arquivos Python compilam, os scripts de shell passam em bash -n e os JSON são válidos"
CONSERTO = "Conserte o erro de sintaxe indicado: o arquivo precisa ser lido pelo interpretador."
BOM = "﻿"


def _erro_de_python(caminho, texto):
    try:
        compile(texto.lstrip(BOM), caminho, "exec", dont_inherit=True)
    except SyntaxError as erro:
        return f"linha {erro.lineno or 0}: {erro.msg}"
    except ValueError as erro:
        return str(erro)
    return None


def _erro_de_json(texto):
    try:
        json.loads(texto.lstrip(BOM))
    except json.JSONDecodeError as erro:
        return f"linha {erro.lineno}: {erro.msg}"
    return None


def _erro_de_shell(dados):
    resposta = subprocess.run(["bash", "-n"], input=dados, capture_output=True, check=False)
    if resposta.returncode == 0:
        return None
    linhas = resposta.stderr.decode("utf-8", errors="replace").strip().splitlines()
    return linhas[0] if linhas else "erro de sintaxe"


def _erro_do_arquivo(ctx, entrada, texto, tem_bash):
    extensao = Path(entrada.caminho).suffix.lower()
    if extensao == ".py":
        return _erro_de_python(entrada.caminho, texto)
    if extensao == ".sh" and tem_bash:
        return _erro_de_shell(ctx.ler(entrada))
    if any(casa(glob, entrada.caminho) for glob in ctx.limites["sintaxe"]["json"]):
        return _erro_de_json(texto)
    return None


def verificar(ctx):
    tem_bash = shutil.which("bash") is not None
    achados = []
    for entrada in ctx.alvos:
        if ctx.excecao(ID, entrada.caminho):
            continue
        texto = ctx.texto(entrada)
        if texto is None:
            continue
        erro = _erro_do_arquivo(ctx, entrada, texto, tem_bash)
        if erro:
            achados.append(Achado(ID, entrada.caminho, erro))
    if not tem_bash and any(e.caminho.endswith(".sh") for e in ctx.alvos):
        ctx.avisos.append("sintaxe: bash não encontrado, os .sh não foram conferidos")
    return achados
