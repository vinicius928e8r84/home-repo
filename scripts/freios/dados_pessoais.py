import os
import re
import unicodedata
from pathlib import Path

from scripts.freios.contexto import Achado

ID = "dados_pessoais"
TITULO = "Nenhum e-mail, IP, caminho de usuário ou nome de pessoa nas linhas novas"
CONSERTO = (
    "Troque o dado por um exemplo: e-mail @example.com (ou o noreply do GitHub), IP de documentação "
    "(192.0.2.x, 198.51.100.x, 203.0.113.x) ou 127.0.0.1, caminho com <usuário>, $USER, ~ ou %USERPROFILE% no lugar do nome. "
    "O valor não é mostrado de propósito: este log pode ser público. Se o dado já foi publicado numa branch, "
    "apagar o commit depois não o recupera. "
    "Os nomes vêm de uma lista fora do repositório: o arquivo apontado por FREIOS_NOMES ou ~/.config/freios/nomes.txt, "
    "um nome por linha (# comenta). "
    "Uma exceção é um glob com motivo em scripts/freios/excecoes.json, só por PR revisada pelo dono. "
    "Só o dado novo reprova: o que já estava na main fica no teto dela."
)
VARIAVEL_DA_LISTA = "FREIOS_NOMES"
LISTA_PADRAO = (".config", "freios", "nomes.txt")
AVISO_SEM_LISTA = (
    "dados_pessoais: sem lista de nomes (aponte FREIOS_NOMES para um arquivo ou crie ~/.config/freios/nomes.txt, "
    "um nome por linha); nesta máquina só e-mail, IP e caminho são conferidos"
)

EMAIL = re.compile(r"(?<![\w.%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(?![\w-])")
ENDERECOS_SEM_DONO = {"noreply", "no-reply", "git"}
DOMINIOS_DE_EXEMPLO = ("example.com", "example.net", "example.org", "exemplo.com", "exemplo.com.br", "noreply.github.com")
FINAIS_RESERVADOS = {"example", "test", "invalid", "localhost"}

IP = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?!\w|\.\d)")
PRIMEIROS_OCTETOS_DE_EXEMPLO = {0, 127, 255}
FAIXAS_DE_DOCUMENTACAO = {(192, 0, 2), (198, 51, 100), (203, 0, 113)}

CAMINHO_NO_WINDOWS = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]{1,2}(?i:Users)[\\/]{1,2}([^\\/\s\"'`:]+)")
CAMINHO_NO_MAC = re.compile(r"(?<![\w:.~$%}-])/Users/([^\\/\s\"'`:]+)")
INICIO_DE_MARCADOR = ("<", "$", "%", "{", "[", "(", "*", "~", ".", "…")
PASTAS_GENERICAS = {"public", "default", "shared", "all", "user", "username", "usuario", "usuário", "nome", "name"}


def _dominio_de_exemplo(dominio):
    if dominio.rsplit(".", 1)[-1] in FINAIS_RESERVADOS:
        return True
    return any(dominio == base or dominio.endswith("." + base) for base in DOMINIOS_DE_EXEMPLO)


def _email_pessoal(linha):
    for achado in EMAIL.finditer(linha):
        local = achado.group(0).rsplit("@", 1)[0].lower()
        if local not in ENDERECOS_SEM_DONO and not _dominio_de_exemplo(achado.group(1).lower()):
            return True
    return False


def _ip_real(linha):
    for achado in IP.finditer(linha):
        octetos = tuple(int(parte) for parte in achado.groups())
        if max(octetos) > 255 or octetos[0] in PRIMEIROS_OCTETOS_DE_EXEMPLO or octetos[:3] in FAIXAS_DE_DOCUMENTACAO:
            continue
        return True
    return False


def _nome_de_pessoa(nome):
    return not (nome.startswith(INICIO_DE_MARCADOR) or nome.lower() in PASTAS_GENERICAS)


def _caminho_pessoal(linha):
    achados = list(CAMINHO_NO_WINDOWS.finditer(linha)) + list(CAMINHO_NO_MAC.finditer(linha))
    return any(_nome_de_pessoa(achado.group(1)) for achado in achados)


def _dobrar(texto):
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return sem_acento.casefold()


def _padrao_dos_nomes(nomes):
    partes = [re.escape(_dobrar(nome)) for nome in nomes]
    return re.compile(r"(?<!\w)(?:" + "|".join(partes) + r")(?!\w)") if partes else None


def _caminho_da_lista():
    apontado = os.environ.get(VARIAVEL_DA_LISTA)
    return Path(apontado) if apontado else Path.home().joinpath(*LISTA_PADRAO)


def _nomes_da_lista(ctx):
    try:
        linhas = _caminho_da_lista().read_text(encoding="utf-8").splitlines()
    except (OSError, RuntimeError, UnicodeDecodeError):
        ctx.avisos.append(AVISO_SEM_LISTA)
        return None
    return _padrao_dos_nomes([linha.strip() for linha in linhas if linha.strip() and not linha.startswith("#")])


def _tipos_da_linha(linha, nomes):
    tipos = []
    if "@" in linha and _email_pessoal(linha):
        tipos.append("e-mail")
    if "." in linha and _ip_real(linha):
        tipos.append("endereço IP")
    if "users" in linha.lower() and _caminho_pessoal(linha):
        tipos.append("caminho com o nome de um usuário")
    if nomes and nomes.search(_dobrar(linha)):
        tipos.append("nome da lista de nomes proibidos")
    return tipos


def _achados_do_texto(caminho, texto, nomes):
    achados = []
    for numero, linha in enumerate(texto.split("\n"), start=1):
        for tipo in _tipos_da_linha(linha, nomes):
            achados.append(Achado(ID, caminho, f"{tipo} (o valor não é mostrado)", numero))
    return achados


def verificar(ctx):
    nomes = _nomes_da_lista(ctx)
    achados = []
    for entrada in ctx.alvos:
        if ctx.excecao(ID, entrada.caminho):
            continue
        texto = ctx.texto(entrada)
        if texto is not None:
            achados += _achados_do_texto(entrada.caminho, texto, nomes)
    return achados
