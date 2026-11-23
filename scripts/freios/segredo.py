import re

from scripts.freios.contexto import Achado, casa

ID = "segredo"
TITULO = "Nenhum segredo, chave, token ou arquivo de credencial"
CONSERTO = (
    "Tire o segredo do arquivo e leia-o do ambiente ou de uma pasta fora do repositório. "
    "Se ele já foi publicado numa branch, considere-o vazado: revogue e troque a chave, "
    "porque apagar o commit depois não o recupera."
)

PADROES = [
    ("chave privada", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("chave de acesso da AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("chave de API do Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("token do GitHub", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("token do Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("chave de API (sk-)", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("token de bot do Telegram", re.compile(r"(?:\b|(?<=bot))\d{8,10}:[A-Za-z0-9_-]{35}\b")),
]
URL_COM_SENHA = re.compile(r"[a-z][a-z0-9+.-]{1,20}://[^\s/:@'\"]{1,100}:([^\s/@'\"]{4,200})@[^\s'\"]{1,200}", re.I)
HOST_DE_EXEMPLO = re.compile(r"^(?:[\w-]+\.)*(?:exemplo|example)\.(?:com|net|org)(?::\d+)?(?:[/?#]|$)", re.I)
SENHA_DE_EXEMPLO = re.compile(
    r"^(?:senha|password|passwd|pass|pwd|secret|segredo|usuario|user|username|usr|xxx+|\*+|porta|port|host"
    r"|s3nh[a0-9]*|<[^>]*>|\{[^}]*\}|\$\{?\w*\}?|%\w*|\.\.\.)$",
    re.I,
)
ATRIBUICAO = re.compile(
    r"(?:secret|passwd|password|senha|api[_-]?key|apikey|token|private[_-]?key|auth[_-]?key|access[_-]?key)"
    r"[\w.-]{0,60}['\"]?\s{0,5}[:=]\s{0,5}['\"]([^'\"\s]{16,512})",
    re.I,
)
PLACEHOLDER = re.compile(
    r"x{4,}|\*{3,}|example|exemplo|sample|your|seu[_-]|changeme|placeholder|dummy|fake|falso|<[^>]*>"
    r"|\$\{|^\$[A-Za-z_(]|%\(|\{\{|process\.env|os\.environ|\.\.\.",
    re.I,
)
TRECHO_LEGIVEL = re.compile(rb"[\x20-\x7e]{12,}")
TAMANHO_DA_JANELA = 2000
SOBRA_ENTRE_JANELAS = 200
CLASSES_DE_CARACTERE = [re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"\d"), re.compile(r"[^A-Za-z0-9]")]


def parece_segredo(valor):
    if PLACEHOLDER.search(valor):
        return False
    if re.fullmatch(r"[0-9a-fA-F]{32,}", valor):
        return True
    classes = sum(1 for classe in CLASSES_DE_CARACTERE if classe.search(valor))
    return classes >= 3 and len(set(valor)) >= 8


def _url_com_senha(texto):
    for achado in URL_COM_SENHA.finditer(texto):
        url = achado.group(0)
        resto = re.split(r"[/?#]", url[url.index("@") + 1:])[0]
        invertida = achado.group(1).isdigit() and len(achado.group(1)) <= 5 and ":" in resto
        host = url[url.index("://") + 3:].split(":")[0] if invertida else resto
        if HOST_DE_EXEMPLO.search(host):
            continue
        senha = resto[resto.index(":") + 1:] if invertida else achado.group(1).split(":")[-1]
        if not SENHA_DE_EXEMPLO.fullmatch(senha):
            return "URL com usuário e senha"
    return None


def achar_na_janela(texto):
    for nome, padrao in PADROES:
        if padrao.search(texto):
            return nome
    if _url_com_senha(texto):
        return "URL com usuário e senha"
    atribuicao = ATRIBUICAO.search(texto)
    if atribuicao and parece_segredo(atribuicao.group(1)):
        return "valor literal em campo de segredo"
    return None


def achar_na_linha(texto):
    if len(texto) <= TAMANHO_DA_JANELA:
        return achar_na_janela(texto)
    passo = TAMANHO_DA_JANELA - SOBRA_ENTRE_JANELAS
    for inicio in range(0, len(texto), passo):
        nome = achar_na_janela(texto[inicio:inicio + TAMANHO_DA_JANELA])
        if nome:
            return nome
    return None


def _achados_do_texto(caminho, texto):
    achados = []
    for numero, linha in enumerate(texto.split("\n"), start=1):
        nome = achar_na_linha(linha)
        if nome:
            achados.append(Achado(ID, caminho, f"parece {nome} (o valor não é mostrado)", numero))
    return achados


def _achados_do_binario(caminho, dados):
    for trecho in TRECHO_LEGIVEL.finditer(dados):
        nome = achar_na_linha(trecho.group(0).decode("ascii"))
        if nome:
            return [Achado(ID, caminho, f"binário com texto que parece {nome} (o valor não é mostrado)")]
    return []


def verificar(ctx):
    proibidos = ctx.limites["segredo"]["arquivos_proibidos"]
    achados = []
    for entrada in ctx.alvos:
        caminho = entrada.caminho
        if ctx.excecao(ID, caminho):
            continue
        if any(casa(glob, caminho) for glob in proibidos):
            achados.append(Achado(ID, caminho, "arquivo de segredo, chave ou sessão não entra no repositório"))
            continue
        dados = ctx.ler(entrada)
        if dados is None:
            continue
        texto = ctx.texto(entrada)
        achados += _achados_do_texto(caminho, texto) if texto is not None else _achados_do_binario(caminho, dados)
    return achados
