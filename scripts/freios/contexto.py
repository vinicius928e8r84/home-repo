import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

PASTA = Path(__file__).resolve().parent
RAIZ_PADRAO = PASTA.parents[1]
MODO_LINK = "120000"
BYTES_PARA_LER_NO_INICIO = 8000


@dataclass(frozen=True)
class Achado:
    verificacao: str
    arquivo: str
    detalhe: str
    linha: int = 0
    medida: int = 1
    grupo: str = ""


@dataclass(frozen=True)
class Entrada:
    caminho: str
    modo: str = "100644"
    sha: str = ""


def carregar_json(nome):
    return json.loads((PASTA / nome).read_text(encoding="utf-8"))


def casa(glob, caminho):
    if glob.endswith("/"):
        base = glob.rstrip("/")
        if "/" not in base:
            return ("/" + caminho).find("/" + glob) >= 0
        return caminho.startswith(glob)
    if "/" not in glob:
        return re.fullmatch(_regex_do_glob(glob), posixpath.basename(caminho)) is not None
    return re.fullmatch(_regex_do_glob(glob), caminho) is not None


def _regex_do_glob(glob):
    partes = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            partes.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            partes.append(".*")
            i += 2
        else:
            partes.append(_regex_do_caractere(glob[i]))
            i += 1
    return "".join(partes)


def _regex_do_caractere(caractere):
    if caractere == "*":
        return "[^/]*"
    if caractere == "?":
        return "[^/]"
    return re.escape(caractere)


def parece_binario(dados):
    return b"\0" in dados[:BYTES_PARA_LER_NO_INICIO]


@dataclass(frozen=True)
class Selecao:
    universo: list
    alvos: list


@dataclass(frozen=True)
class Configuracao:
    limites: dict
    excecoes: dict
    base: str = None
    execucao: str = "tudo"


class Contexto:
    def __init__(self, raiz, selecao, leitor, configuracao):
        self.raiz = raiz
        self.universo = list(selecao.universo)
        self.alvos = [e for e in selecao.alvos if e.modo != MODO_LINK]
        self.leitor = leitor
        self.limites = configuracao.limites
        self.excecoes = configuracao.excecoes
        self.base = configuracao.base
        self.execucao = configuracao.execucao
        self.avisos = []
        self._cache = {}
        self.links = {e.caminho: self._alvo_do_link(e) for e in self.universo if e.modo == MODO_LINK}
        self.arquivos = {e.caminho: e for e in self.universo if e.modo != MODO_LINK}
        self.pastas = {p for c in list(self.arquivos) + list(self.links) for p in _pastas_de(c)}

    def _alvo_do_link(self, entrada):
        return self.leitor(entrada).decode("utf-8", errors="replace").strip()

    def ler(self, entrada):
        if entrada.caminho not in self._cache:
            self._cache[entrada.caminho] = self._ler_ou_nada(entrada)
        return self._cache[entrada.caminho]

    def _ler_ou_nada(self, entrada):
        try:
            return self.leitor(entrada)
        except OSError:
            return None

    def texto(self, entrada):
        dados = self.ler(entrada)
        if dados is None or parece_binario(dados):
            return None
        return dados.decode("utf-8", errors="replace")

    def excecao(self, verificacao, caminho):
        return any(casa(item["glob"], caminho) for item in self.excecoes.get(verificacao, []))

    def entradas_com_extensao(self, extensoes):
        return [e for e in self.alvos if Path(e.caminho).suffix.lower() in extensoes]

    def existe(self, caminho):
        atual = posixpath.normpath(caminho)
        for _ in range(16):
            if atual == "." or atual in self.arquivos or atual in self.links or atual in self.pastas:
                return True
            atual = self._seguir_link(atual)
            if atual is None:
                return False
        return False

    def _seguir_link(self, caminho):
        partes = caminho.split("/")
        for i in range(1, len(partes)):
            prefixo = "/".join(partes[:i])
            if prefixo in self.links:
                destino = posixpath.normpath(posixpath.join(posixpath.dirname(prefixo), self.links[prefixo]))
                return posixpath.join(destino, *partes[i:])
        return None


def _pastas_de(caminho):
    partes = caminho.split("/")[:-1]
    return ["/".join(partes[: i + 1]) for i in range(len(partes))]


@dataclass
class Resultado:
    verificacao: object
    achados: list = field(default_factory=list)
