import ast
import io
import re
import tokenize
from bisect import bisect_right

PALAVRAS_ANTES_DE_REGEX = {
    "return", "typeof", "case", "of", "in", "void", "delete", "throw", "new", "else", "do", "yield", "await",
}
ULTIMA_PALAVRA = re.compile(r"[\w$]+$")

JS = re.compile(
    r"(?P<linha>//[^\n]*)"
    r"|(?P<bloco>/\*[\s\S]*?(?:\*/|$))"
    r"|(?P<texto>'(?:\\[\s\S]|[^'\\\n])*'?|\"(?:\\[\s\S]|[^\"\\\n])*\"?)"
    r"|(?P<molde>`)"
    r"|(?P<regex>/(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n\[*])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n\[])*/[a-z]*)"
    r"|(?P<abre>\{)"
    r"|(?P<fecha>\})"
)
MOLDE = re.compile(r"\\[\s\S]|`|\$\{")

SHELL = re.compile(
    r"(?P<heredoc>(?<!<)<<-?[ \t]*(?P<aspas>['\"]?)(?P<palavra>[A-Za-z_][A-Za-z_0-9]*)(?P=aspas))"
    r"|(?P<ansi>\$'(?:\\[\s\S]|[^'\\])*')"
    r"|(?P<simples>'[^']*')"
    r"|(?P<dupla>\"(?:\\[\s\S]|[^\"\\])*\")"
    r"|(?P<expansao>\$\{[^}]*\})"
    r"|(?P<cifrao>\$[\s\S])"
    r"|(?P<escape>\\[\s\S])"
    r"|(?P<comentario>\#[^\n]*)"
    r"|(?P<novalinha>\n)"
)
INICIO_DE_PALAVRA_SHELL = " \t\n;&|(){}<>"

POWERSHELL = re.compile(
    r"(?P<aqui>@\"\r?\n[\s\S]*?\r?\n\"@|@'\r?\n[\s\S]*?\r?\n'@)"
    r"|(?P<bloco><\#[\s\S]*?(?:\#>|$))"
    r"|(?P<texto>'(?:''|[^'])*'|\"(?:`[\s\S]|\"\"|[^\"`])*\")"
    r"|(?P<comentario>\#[^\n]*)"
)

TOML = re.compile(
    r"(?P<texto>\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|\"(?:\\.|[^\"\\\n])*\"|'[^'\n]*')"
    r"|(?P<comentario>\#[^\n]*)"
)

TEXTO_DE_YAML = re.compile(r"'(?:''|[^'\n])*'|\"(?:\\.|[^\"\\\n])*\"")
COMENTARIO_DE_YAML = re.compile(r"(?:^|\s)(\#.*)$")
BLOCO_DE_YAML = re.compile(r"[:-][ \t]+[|>][+-]?[0-9]?$")


class Estado:
    def __init__(self, pos):
        self.pos = pos
        self.achados = []
        self.profundidade = 0
        self.fim = False
        self.pendentes = []


def _inicio_de_palavra(texto, inicio, permitidos):
    return inicio == 0 or texto[inicio - 1] in permitidos


def _depois_de_operando(texto, inicio):
    antes = texto[max(0, inicio - 40):inicio].rstrip()
    if not antes:
        return False
    if antes[-1] in ")]":
        return True
    palavra = ULTIMA_PALAVRA.search(antes)
    return palavra is not None and palavra.group(0) not in PALAVRAS_ANTES_DE_REGEX


def _js_comentario(texto, m, estado, em_molde):
    estado.achados.append((m.start(), m.end()))


def _js_ignorar(texto, m, estado, em_molde):
    return None


def _js_regex(texto, m, estado, em_molde):
    if _depois_de_operando(texto, m.start()):
        estado.pos = m.start() + 1


def _js_molde(texto, m, estado, em_molde):
    achados, estado.pos = _escanear_molde(texto, m.end())
    estado.achados += achados


def _js_abre(texto, m, estado, em_molde):
    estado.profundidade += 1


def _js_fecha(texto, m, estado, em_molde):
    if not em_molde:
        return
    if estado.profundidade == 0:
        estado.fim = True
    else:
        estado.profundidade -= 1


TRATADORES_JS = {
    "linha": _js_comentario,
    "bloco": _js_comentario,
    "texto": _js_ignorar,
    "regex": _js_regex,
    "molde": _js_molde,
    "abre": _js_abre,
    "fecha": _js_fecha,
}


def _escanear_js(texto, pos, em_molde):
    estado = Estado(pos)
    while not estado.fim:
        m = JS.search(texto, estado.pos)
        if m is None:
            estado.pos = len(texto)
            break
        estado.pos = m.end()
        TRATADORES_JS[m.lastgroup](texto, m, estado, em_molde)
    return estado.achados, estado.pos


def _escanear_molde(texto, pos):
    achados = []
    while True:
        m = MOLDE.search(texto, pos)
        if m is None:
            return achados, len(texto)
        pos = m.end()
        if m.group(0) == "`":
            return achados, pos
        if m.group(0) == "${":
            internos, pos = _escanear_js(texto, pos, True)
            achados += internos


def comentarios_js(texto):
    return _escanear_js(texto, 0, False)[0]


def _pular_heredocs(texto, estado):
    for palavra in estado.pendentes:
        fim = re.compile(r"^[ \t]*" + re.escape(palavra) + r"[ \t]*$", re.M).search(texto, estado.pos)
        estado.pos = fim.end() if fim else len(texto)
    estado.pendentes = []


def _shell_comentario(texto, m, estado):
    if _inicio_de_palavra(texto, m.start(), INICIO_DE_PALAVRA_SHELL):
        estado.achados.append((m.start(), m.end()))
    else:
        estado.pos = m.start() + 1


def _shell_heredoc(texto, m, estado):
    estado.pendentes.append(m.group("palavra"))


def _shell_novalinha(texto, m, estado):
    if estado.pendentes:
        _pular_heredocs(texto, estado)


def _shell_ignorar(texto, m, estado):
    return None


TRATADORES_SHELL = {
    "heredoc": _shell_heredoc,
    "comentario": _shell_comentario,
    "novalinha": _shell_novalinha,
}


def comentarios_shell(texto):
    estado = Estado(0)
    while True:
        m = SHELL.search(texto, estado.pos)
        if m is None:
            return estado.achados
        estado.pos = m.end()
        TRATADORES_SHELL.get(m.lastgroup, _shell_ignorar)(texto, m, estado)


def _varrer_simples(texto, padrao, tipos_de_comentario, inicio_valido):
    achados = []
    pos = 0
    while True:
        m = padrao.search(texto, pos)
        if m is None:
            return achados
        pos = m.end()
        if m.lastgroup not in tipos_de_comentario:
            continue
        if inicio_valido(texto, m.start()):
            achados.append((m.start(), m.end()))
        else:
            pos = m.start() + 1


def comentarios_powershell(texto):
    return _varrer_simples(
        texto, POWERSHELL, {"comentario", "bloco"},
        lambda t, i: _inicio_de_palavra(t, i, INICIO_DE_PALAVRA_SHELL),
    )


def comentarios_toml(texto):
    return _varrer_simples(texto, TOML, {"comentario"}, lambda t, i: True)


def _comentario_de_yaml(linha):
    sem_textos = TEXTO_DE_YAML.sub(lambda m: " " * len(m.group(0)), linha)
    achado = COMENTARIO_DE_YAML.search(sem_textos)
    return (achado.start(1), sem_textos[: achado.start(1)]) if achado else (None, sem_textos)


def comentarios_yaml(texto):
    achados = []
    deslocamento = 0
    bloco = None
    for linha in texto.split("\n"):
        recuo = len(linha) - len(linha.lstrip())
        dentro = bloco is not None and (not linha.strip() or recuo > bloco)
        if not dentro:
            bloco = None
            inicio, codigo = _comentario_de_yaml(linha)
            if inicio is not None:
                achados.append((deslocamento + inicio, deslocamento + len(linha)))
            if BLOCO_DE_YAML.search(codigo.rstrip()):
                bloco = recuo
        deslocamento += len(linha) + 1
    return achados


def _deslocamentos_de_linha(texto):
    return [0] + [i + 1 for i, c in enumerate(texto) if c == "\n"]


def trechos_em_linhas(texto, intervalos):
    deslocamentos = _deslocamentos_de_linha(texto)
    resultado = []
    for inicio, fim in sorted(intervalos):
        linha = bisect_right(deslocamentos, inicio)
        resultado.append((linha, texto[inicio:fim]))
    return resultado


def comentarios_python(texto):
    achados = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(texto).readline):
            if token.type == tokenize.COMMENT:
                achados.append((token.start[0], token.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return achados + _textos_soltos_de_python(texto)


def _textos_soltos_de_python(texto):
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return []
    achados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant) and isinstance(no.value.value, str):
            achados.append((no.lineno, no.value.value.strip().split("\n")[0]))
    return achados


COMENTARIOS_POR_EXTENSAO = {
    ".py": None,
    ".ts": comentarios_js,
    ".mts": comentarios_js,
    ".js": comentarios_js,
    ".mjs": comentarios_js,
    ".cjs": comentarios_js,
    ".sh": comentarios_shell,
    ".ps1": comentarios_powershell,
    ".yml": comentarios_yaml,
    ".yaml": comentarios_yaml,
    ".toml": comentarios_toml,
}


def achar_comentarios(extensao, texto):
    if extensao == ".py":
        return sorted(comentarios_python(texto))
    intervalos = COMENTARIOS_POR_EXTENSAO[extensao](texto)
    return trechos_em_linhas(texto, intervalos)
