import posixpath
import re
from pathlib import Path
from urllib.parse import unquote

from scripts.freios.contexto import Achado

ID = "links"
TITULO = "Todo link relativo dos .md aponta para um arquivo que existe"
CONSERTO = (
    "Corrija o caminho do link, ou crie o arquivo para o qual ele aponta. "
    "O caminho é relativo à pasta do .md e o arquivo precisa estar no git."
)
BLOCO_DE_CODIGO = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n[\s\S]*?(?:^[ \t]*\1[ \t]*$|\Z)", re.M)
CODIGO_EM_LINHA = re.compile(r"(`+)[^`\n]*?\1")
LINK_EM_LINHA = re.compile(r"\]\(\s*<?([^()\s>]+(?:\([^()\s]*\)[^()\s>]*)*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
LINK_DE_REFERENCIA = re.compile(r"^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*<?(\S+?)>?(?:[ \t]+.*)?$", re.M)
ESQUEMA = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def sem_codigo(texto):
    sem_blocos = BLOCO_DE_CODIGO.sub(lambda m: "\n" * m.group(0).count("\n"), texto)
    return CODIGO_EM_LINHA.sub(lambda m: " " * len(m.group(0)), sem_blocos)


def destinos(texto):
    limpo = sem_codigo(texto)
    achados = []
    for padrao in (LINK_EM_LINHA, LINK_DE_REFERENCIA):
        for m in padrao.finditer(limpo):
            achados.append((limpo.count("\n", 0, m.start()) + 1, m.group(1)))
    return sorted(achados)


def _caminho_do_destino(origem, destino):
    if not destino or destino.startswith(("#", "/")) or ESQUEMA.match(destino):
        return None
    sem_ancora = re.split(r"[#?]", destino, maxsplit=1)[0]
    if not sem_ancora:
        return None
    return posixpath.normpath(posixpath.join(posixpath.dirname(origem), unquote(sem_ancora)))


def verificar(ctx):
    achados = []
    for caminho in sorted(ctx.arquivos):
        if Path(caminho).suffix.lower() != ".md" or ctx.excecao(ID, caminho):
            continue
        texto = ctx.texto(ctx.arquivos[caminho])
        if texto is None:
            continue
        for linha, destino in destinos(texto):
            alvo = _caminho_do_destino(caminho, destino)
            if alvo is not None and not ctx.existe(alvo):
                achados.append(Achado(ID, caminho, f"o link {destino} não aponta para um arquivo do repositório", linha))
    return achados
