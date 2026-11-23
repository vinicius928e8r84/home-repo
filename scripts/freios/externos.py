import shutil
import subprocess
from pathlib import Path

from scripts.freios.contexto import Achado

ID = "externos"
TITULO = "As ferramentas de lint do repo (ruff, ESLint) passam quando estão configuradas"
CONSERTO = "Conserte o que a ferramenta aponta; a configuração dela fica no repositório."
LINHAS_DA_SAIDA = 25


def _configurada(ctx, ferramenta):
    return any((Path(ctx.raiz) / caminho).exists() for caminho in ferramenta["quando_existe"])


def _alvos(ctx, ferramenta):
    if ctx.execucao != "commit":
        return list(ferramenta["alvo_tudo"])
    extensoes = set(ferramenta["extensoes"])
    return [e.caminho for e in ctx.alvos if Path(e.caminho).suffix.lower() in extensoes]


def _rodar(ctx, ferramenta, executavel, alvos):
    comando = [executavel, *ferramenta["comando"][1:], *alvos]
    resposta = subprocess.run(comando, cwd=ctx.raiz, capture_output=True, check=False)
    if resposta.returncode == 0:
        return []
    saida = (resposta.stdout + b"\n" + resposta.stderr).decode("utf-8", errors="replace")
    linhas = [linha for linha in saida.splitlines() if linha.strip()]
    detalhe = "\n".join(linhas[:LINHAS_DA_SAIDA])
    if len(linhas) > LINHAS_DA_SAIDA:
        detalhe += f"\n... e mais {len(linhas) - LINHAS_DA_SAIDA} linhas (rode {ferramenta['nome']} para ver tudo)"
    return [Achado(ID, "", f"{ferramenta['nome']} falhou:\n{detalhe}")]


def _verificar_ferramenta(ctx, ferramenta):
    if not _configurada(ctx, ferramenta):
        ctx.avisos.append(f"{ferramenta['nome']}: ainda sem configuração no repositório, pulado")
        return []
    alvos = _alvos(ctx, ferramenta)
    if not alvos:
        return []
    executavel = shutil.which(ferramenta["comando"][0])
    if executavel is None:
        detalhe = f"{ferramenta['nome']} está configurado mas o comando {ferramenta['comando'][0]} não foi encontrado"
        return [Achado(ID, "", detalhe)]
    return _rodar(ctx, ferramenta, executavel, alvos)


def verificar(ctx):
    achados = []
    for ferramenta in ctx.limites["ferramentas"]:
        achados += _verificar_ferramenta(ctx, ferramenta)
    return achados
