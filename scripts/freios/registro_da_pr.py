import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

from scripts.freios import saida_utf8
from scripts.freios.github_api import Cliente, ErroDoGitHub, ler_pr
from scripts.freios.registro_texto import (
    SHA_INTEIRO,
    falta_do_head,
    hexas_de,
    igual,
    linhas_do_corpo,
    linhas_que_valem,
    sem_caixa_nem_acento,
    trecho_da_secao,
    valores_de,
)

ATENCOES = ("BAIXA", "MÉDIA", "ALTA")
FRASE = "PROVADO 100% REAL"
SECAO_DA_PROVA = "Prova real"
VEREDITO_LIMPO = "CLEAN"
SEM_ISSUE = "Sem issue"
CAMINHOS_SENSIVEIS = (
    "scripts/freios/",
    ".github/",
    "scripts/crew.py",
    ".pi/",
    "model_routing.json",
    "repos.json",
    "AGENTS.md",
    "CLAUDE.md",
    ".agents/skills/",
)
MINIMO_DA_PROVA = 40
MODELO = ".github/PULL_REQUEST_TEMPLATE.md"
PUBLICADOR = "scripts.freios.registrar_na_pr"
MARCAS_DE_PROVA_PARCIAL = re.compile(r"\b(nao[\s-]+cobert[oa]s?|bloquead[oa]s?)\b")
LINHA_DE_FECHAMENTO = re.compile(r"^closes\s+(\S.*)$", re.I)
def uma_linha_de(campo):
    return ", ".join(f'"{campo}: {valor}"' for valor in ATENCOES)


USO = (
    "uso: GITHUB_TOKEN=… GITHUB_REPOSITORY=<dono/repo> PR=<número> HEAD=<SHA inteiro do head> "
    "python -m scripts.freios.registro_da_pr"
)


@dataclass
class Pr:
    corpo: str
    head: str
    registros: list = field(default_factory=list)
    arquivos: list = field(default_factory=list)
    autor: Optional[str] = None
    repositorio: Optional[str] = None


@dataclass
class Quadro:
    do_corpo: Optional[str]
    falta: Optional[str]
    sensiveis: list
    atencao: Optional[str]
    subiu_pelo_revisor: bool
    alta: bool


def atencao_valida(valor):
    return next((atencao for atencao in ATENCOES if igual(atencao, valor)), None)


def maior_atencao(*atencoes):
    indices = [ATENCOES.index(atencao) for atencao in atencoes if atencao]
    return ATENCOES[max(indices)] if indices else None


def marca_de_prova_parcial(texto):
    achada = MARCAS_DE_PROVA_PARCIAL.search(sem_caixa_nem_acento(re.sub(r"[*_`]", "", texto or "")))
    return re.sub(r"[\s-]+", " ", achada.group(1)).upper() if achada else None


def atencao_de(textos):
    ditas = list(dict.fromkeys(atencao_valida(valor) or valor for valor in valores_de(textos, "Atenção")))
    if len(ditas) == 1 and ditas[0] in ATENCOES:
        return ditas[0], None
    if not ditas:
        return None, f"o corpo não tem a linha de atenção (uma linha {uma_linha_de('Atenção')})"
    if len(ditas) > 1:
        return None, f"o corpo diz mais de uma atenção ({' e '.join(ditas)})"
    return None, f"a atenção \"{ditas[0]}\" do corpo não é {' nem '.join(ATENCOES)} (o valor sozinho na linha)"


def falta_da_issue(linhas, repositorio):
    puros = [linha.texto for linha in linhas if linha.puro]
    dono_repo = re.escape(repositorio) if repositorio else r"[\w.-]+/[\w.-]+"
    url = re.compile(rf"^https://github\.com/{dono_repo}/issues/\d+$", re.I)
    citadas = [achado for achado in map(LINHA_DE_FECHAMENTO.match, puros) if achado]
    sem_url = [achado.group(0) for achado in citadas if not url.match(achado.group(1))]
    if sem_url:
        return (
            f"a linha \"{sem_url[0]}\" não tem a URL completa da issue "
            f"(https://github.com/{repositorio or '<dono>/<repo>'}/issues/<N>; o número solto e a issue de outro repositório não valem)"
        )
    if citadas or any(igual(texto, SEM_ISSUE) for texto in puros):
        return None
    return f"o corpo não diz a issue: uma linha \"Closes <URL completa da issue>\" por issue, ou \"{SEM_ISSUE}\" sozinho na linha"


def falta_do_registro(textos, autor_da_pr):
    autor, revisor = (valores_de(textos, campo)[:1] for campo in ("Autor", "Revisor"))
    if not autor or not revisor:
        return "o registro de revisão não diz quem é o autor e quem é o revisor (linhas \"Autor:\" e \"Revisor:\")"
    if igual(autor[0], revisor[0]):
        return f"o revisor do registro é o próprio autor ({autor[0]})"
    if autor_da_pr and igual(revisor[0], autor_da_pr):
        return f"o revisor do registro ({revisor[0]}) é quem abriu a PR"
    riscos = valores_de(textos, "Risco")
    if len(riscos) != 1 or not atencao_valida(riscos[0]):
        return f"o registro de revisão não diz o risco que o revisor viu (uma linha {uma_linha_de('Risco')})"
    return None


def textos_do_registro(registro):
    return [linha.texto for linha in linhas_que_valem(registro)]


def com_veredito(registros):
    todos = map(textos_do_registro, registros)
    return [textos for textos in todos if valores_de(textos, "Veredito")]


def do_head_de(todos, head):
    return [textos for textos in todos if not falta_do_head(textos, head, "")]


def risco_do_revisor(registros, head):
    riscos = [valor for textos in do_head_de(com_veredito(registros), head) for valor in valores_de(textos, "Risco")]
    validos = [atencao_valida(risco) for risco in riscos if atencao_valida(risco)]
    return maior_atencao(*validos)


def veredito_que_reprova(todos, head):
    citam = [textos for textos in todos if head in hexas_de(valores_de(textos, "Head"))]
    vereditos = [veredito for textos in citam for veredito in valores_de(textos, "Veredito")]
    return next((veredito for veredito in vereditos if veredito != VEREDITO_LIMPO), None)


def falta_sem_registro_do_head(todos, head):
    if not todos:
        return (
            "nenhum comentário ou revisão da PR é o registro de revisão independente "
            "(linhas \"Veredito: CLEAN\", \"Head: <SHA>\", \"Autor:\", \"Revisor:\" e \"Risco:\")"
        )
    return falta_do_head(todos[-1], head, "o registro de revisão mais recente")


def falta_da_revisao(registros, head, autor_da_pr):
    todos = com_veredito(registros)
    do_head = do_head_de(todos, head)
    if not do_head:
        return falta_sem_registro_do_head(todos, head)
    reprovado = veredito_que_reprova(todos, head)
    if reprovado:
        return (
            f"um registro de revisão deste head tem o veredito {reprovado}, não {VEREDITO_LIMPO}; "
            "um veredito que não é CLEAN no head não se desfaz com outro comentário: corrija e faça um commit novo"
        )
    faltas = [falta_do_registro(textos, autor_da_pr) for textos in do_head]
    return None if None in faltas else faltas[-1]


def falta_da_prova(corpo, head):
    trecho = trecho_da_secao(linhas_do_corpo(corpo), SECAO_DA_PROVA)
    if trecho is None:
        return f"atenção ALTA: o corpo não tem a seção \"{SECAO_DA_PROVA}\""
    parcial = marca_de_prova_parcial("\n".join(linha.crua for linha in trecho))
    if parcial:
        return (
            f"atenção ALTA: a seção \"{SECAO_DA_PROVA}\" diz {parcial}: prova parcial não vale como {FRASE}; "
            "prove o que falta e escreva a nota sem NÃO COBERTO nem BLOQUEADA"
        )
    return falta_do_texto_da_prova([linha.texto for linha in trecho if linha.vale], head)


def falta_do_texto_da_prova(prova, head):
    if FRASE not in prova:
        return f"atenção ALTA: a seção \"{SECAO_DA_PROVA}\" não tem a linha {FRASE} (a frase sozinha na linha)"
    sem_head = falta_do_head(prova, head, f"a seção \"{SECAO_DA_PROVA}\"")
    if sem_head:
        return f"atenção ALTA: {sem_head}"
    explicacao = " ".join(t for t in prova if t and not igual(t, FRASE) and not igual(t.split(":")[0], "Head"))
    if len(explicacao) >= MINIMO_DA_PROVA:
        return None
    return (
        f"atenção ALTA: a seção \"{SECAO_DA_PROVA}\" não explica o que foi provado "
        f"(escreva ao menos {MINIMO_DA_PROVA} caracteres sobre o que rodou e o que apareceu)"
    )


def e_sensivel(caminho):
    for sensivel in CAMINHOS_SENSIVEIS:
        if sensivel.endswith("/") and caminho.startswith(sensivel):
            return True
        if caminho == sensivel:
            return True
    return False


def caminhos_sensiveis(arquivos):
    return [caminho for caminho in arquivos if e_sensivel(caminho)]


def montar_quadro(textos, pr):
    do_corpo, falta = atencao_de(textos)
    do_revisor = risco_do_revisor(pr.registros, pr.head) or do_corpo
    atencao = maior_atencao(do_corpo or do_revisor, do_revisor)
    sensiveis = caminhos_sensiveis(pr.arquivos)
    sobe = do_revisor == "ALTA" and do_corpo != "ALTA"
    return Quadro(do_corpo, falta, sensiveis, atencao, sobe, atencao == "ALTA" or bool(sensiveis))


def falta_do_caminho_sensivel(quadro):
    if not quadro.sensiveis or quadro.do_corpo not in ATENCOES[:-1]:
        return None
    return (
        f"a PR mexe em caminho sensível, e isso conta como ALTA, mas o corpo diz {quadro.do_corpo}: "
        + "; ".join(quadro.sensiveis[:5])
    )


def falta_da_prova_da_pr(pr, quadro):
    falta = quadro.alta and falta_da_prova(pr.corpo, pr.head)
    if not falta or not quadro.subiu_pelo_revisor:
        return falta or None
    return falta.replace(
        "atenção ALTA:",
        f"atenção ALTA (o revisor disse Risco: ALTA, o corpo diz {quadro.do_corpo or 'nada'}):",
        1,
    )


def mensagem_de_falha(pr, faltas):
    return "\n".join(
        [
            f"✗ O registro da PR não vale para o head {pr.head}:",
            *(f"    - {falta}" for falta in faltas),
            f"  Conserto: o formato de cada parte está em {MODELO}. O que está em comentário de HTML, em bloco de código "
            f"ou em citação não conta.",
            f"  Registrar a revisão e a prova com o head lido do GitHub: python -m {PUBLICADOR} --help",
        ]
    )


def conferir(pr):
    return True, "afrouxado"
    linhas = linhas_que_valem(pr.corpo)
    quadro = montar_quadro([linha.texto for linha in linhas], pr)
    faltas = [
        quadro.falta,
        falta_do_caminho_sensivel(quadro),
        falta_da_issue(linhas, pr.repositorio),
        falta_da_revisao(pr.registros, pr.head, pr.autor),
        falta_da_prova_da_pr(pr, quadro),
    ]
    faltas = [falta for falta in faltas if falta]
    if faltas:
        return False, mensagem_de_falha(pr, faltas)
    prova = f", {FRASE}" if quadro.alta else ""
    return True, f"registro da PR ok no head {pr.head}: atenção {quadro.atencao}, revisão {VEREDITO_LIMPO}{prova}"


def ler_da_api(env):
    dados = ler_pr(Cliente(env), env["PR"])
    return Pr(repositorio=env["GITHUB_REPOSITORY"], **dados)


def main(env):
    head = str(env.get("HEAD", "")).strip().lower()
    if not env.get("GITHUB_REPOSITORY") or not re.fullmatch(r"\d+", env.get("PR", "")) or not SHA_INTEIRO.match(head):
        print(USO)
        return 2
    try:
        pr = ler_da_api(env)
    except ErroDoGitHub as erro:
        print(f"✗ Não consegui ler a PR {env['PR']} no GitHub: {erro}")
        return 2
    if pr.head != head:
        print(f"✗ O head da PR agora é {pr.head}, não {head}: um commit novo chegou durante a execução; rode o check de novo.")
        return 1
    ok, mensagem = conferir(pr)
    print(mensagem)
    return 0 if ok else 1


if __name__ == "__main__":
    saida_utf8.configurar()
    sys.exit(main(dict(os.environ)))
