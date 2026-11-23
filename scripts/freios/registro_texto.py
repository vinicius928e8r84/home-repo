import re
import unicodedata
from typing import NamedTuple

TITULO = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*)$")
CERCA = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CITACAO = re.compile(r"^ {0,3}>")
COMENTARIO_HTML = re.compile(r"<!--.*?(?:-->|$)", re.S)
TEXTO_PURO = re.compile(r"^(?! {4}|\t)[^`]*$")
SHA_INTEIRO = re.compile(r"^[0-9a-f]{40}$")


class Linha(NamedTuple):
    crua: str
    vale: bool
    texto: str
    nivel: int
    puro: bool


def sem_caixa_nem_acento(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if not unicodedata.combining(c)).lower().strip()


def igual(a, b):
    return sem_caixa_nem_acento(a) == sem_caixa_nem_acento(b)


def sem_marcacao(texto):
    return re.sub(r"^[\s-]+|[\s.!]+$", "", re.sub(r"[*_`]", "", texto))


def titulo_de(linha):
    achado = TITULO.match(linha.split("\r")[0])
    if not achado:
        return None
    texto = achado.group(2).rstrip()
    miolo = texto.rstrip("#")
    com_fecho = len(miolo) < len(texto) and (not miolo or miolo[-1].isspace())
    return len(achado.group(1)), (miolo if com_fecho else texto).strip()


def esvaziar(achado):
    return re.sub(r"[^\n]", " ", achado.group(0))


def linhas_sem_comentario(markdown):
    return re.split(r"\r?\n", COMENTARIO_HTML.sub(esvaziar, markdown or ""))


def fecha_a_cerca(marca, cerca, linha):
    return marca[0] == cerca[0] and len(marca) >= len(cerca) and linha.strip() == marca


def proxima_cerca(cerca, abre, crua):
    if not abre:
        return cerca
    if cerca is None:
        return abre.group(1)
    return None if fecha_a_cerca(abre.group(1), cerca, crua) else cerca


def montar_linha(crua, vale):
    if not vale:
        return Linha(crua, False, "", 0, False)
    titulo = titulo_de(crua)
    texto = sem_marcacao(titulo[1] if titulo else crua)
    return Linha(crua, True, texto, titulo[0] if titulo else 0, bool(TEXTO_PURO.match(crua)))


def linhas_do_corpo(markdown):
    cerca = None
    saida = []
    for crua in linhas_sem_comentario(markdown):
        abre = CERCA.match(crua)
        vale = not abre and cerca is None and not CITACAO.match(crua)
        cerca = proxima_cerca(cerca, abre, crua)
        saida.append(montar_linha(crua, vale))
    return saida


def linhas_que_valem(markdown):
    return [linha for linha in linhas_do_corpo(markdown) if linha.vale]


def indice_da_secao(linhas, nome):
    for indice, linha in enumerate(linhas):
        if linha.nivel and igual(linha.texto, nome):
            return indice
    return None


def fim_da_secao(linhas, inicio):
    for indice in range(inicio + 1, len(linhas)):
        if linhas[indice].nivel and linhas[indice].nivel <= linhas[inicio].nivel:
            return indice
    return len(linhas)


def trecho_da_secao(linhas, nome):
    inicio = indice_da_secao(linhas, nome)
    if inicio is None:
        return None
    return linhas[inicio + 1 : fim_da_secao(linhas, inicio)]


def valores_de(textos, campo):
    pares = (texto.split(":", 1) for texto in textos if ":" in texto)
    return [valor.strip() for nome, valor in pares if valor.strip() and igual(nome, campo)]


def hexas_de(textos):
    return re.findall(r"[0-9a-f]+", "\n".join(textos).lower())


def falta_do_head(textos, head, o_que):
    valores = [valor.lower() for valor in valores_de(textos, "Head")]
    if valores and all(valor == head for valor in valores):
        return None
    hexas = hexas_de(valores)
    if head in hexas:
        return f"{o_que} tem na linha \"Head:\" mais do que o SHA do head (uma linha por SHA, só os 40 caracteres)"
    outro = next((hexa for hexa in hexas if SHA_INTEIRO.match(hexa)), None)
    if outro:
        return f"{o_que} é do commit {outro}, que não é o head (o head mudou: o que valia para o commit anterior não vale)"
    if any(len(hexa) >= 7 and head.startswith(hexa) for hexa in hexas):
        return f"{o_que} tem o SHA do head abreviado; escreva os 40 caracteres"
    return f"{o_que} não tem a linha \"Head:\" com o SHA do head"
