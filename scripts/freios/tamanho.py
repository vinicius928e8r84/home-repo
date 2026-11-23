from pathlib import Path

from scripts.freios.contexto import Achado

ID = "tamanho"
TITULO = "Nenhum arquivo de texto acima do teto de bytes nem arquivo de código acima do teto de linhas"
CONSERTO = (
    "Divida o arquivo antes de commitar. Não apague código nem o espreme em menos linhas. "
    "Procure as costuras: grupos de funções, componentes ou testes que mudam juntos e dividem pouco "
    "com o resto. Leve cada grupo para o seu arquivo e divida os testes pelo comportamento testado."
)


def contar_linhas(dados):
    if not dados:
        return 0
    return dados.count(b"\n") + (0 if dados.endswith(b"\n") else 1)


def verificar(ctx):
    teto = ctx.limites["tamanho"]
    codigo = set(teto["extensoes_de_codigo"])
    achados = []
    for entrada in ctx.alvos:
        if ctx.excecao(ID, entrada.caminho):
            continue
        dados = ctx.ler(entrada)
        if dados is None or ctx.texto(entrada) is None:
            continue
        achados += _achados_do_arquivo(entrada.caminho, dados, teto, codigo)
    return achados


def _achados_do_arquivo(caminho, dados, teto, codigo):
    achados = []
    if len(dados) > teto["bytes_maximos"]:
        detalhe = f"{len(dados)} bytes, acima do teto de {teto['bytes_maximos']}"
        achados.append(Achado(ID, caminho, detalhe, medida=len(dados)))
    linhas = contar_linhas(dados)
    if Path(caminho).suffix.lower() in codigo and linhas > teto["linhas_maximas"]:
        detalhe = f"{linhas} linhas, acima do teto de {teto['linhas_maximas']}"
        achados.append(Achado(ID, caminho, detalhe, medida=linhas, grupo=caminho + "#linhas"))
    return achados
