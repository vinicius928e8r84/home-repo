import argparse
import sys
from pathlib import Path

from scripts.freios import (
    autoria, catraca, binario, comentarios, externos, funcoes, links, orcamento, segredo, sintaxe, skills, tamanho, testes,
)
from scripts.freios.git import montar_contexto, raiz_do_repositorio

POR_ARQUIVO = [tamanho, funcoes, comentarios, sintaxe, segredo, binario, externos]
NO_COMMIT = [tamanho, comentarios]
DO_REPOSITORIO = [skills, links, orcamento, autoria, testes]
USO = """Os freios do repositório: tetos de tamanho, sem comentário, sintaxe, segredo, skills, links,
orçamento de contexto e autoria dos commits.

--commit confere o tamanho e os comentários dos arquivos que estão no commit (gancho pre-commit).
--tudo confere o índice inteiro, sem arquivo não rastreado, e os commits da branch contra --base (gancho pre-push e CI).
Sai com 0 quando tudo passa e com 1 quando alguma verificação falha."""
LINHAS_POR_VERIFICACAO = 15


def ler_argumentos(argv):
    analisador = argparse.ArgumentParser(
        prog="freios.py", description=USO, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    modo = analisador.add_mutually_exclusive_group(required=True)
    modo.add_argument("--commit", action="store_const", dest="modo", const="commit")
    modo.add_argument("--tudo", action="store_const", dest="modo", const="tudo")
    analisador.add_argument("--base", default="origin/main", help="ref contra a qual os commits são conferidos")
    analisador.add_argument("--so", action="append", default=[], metavar="ID", help="roda só esta verificação")
    analisador.add_argument("--completo", action="store_true", help="lista todos os achados, sem cortar")
    analisador.add_argument("--criar-linha-de-base", action="store_true", help="cria a linha de base que ainda falta")
    analisador.add_argument(
        "--atualizar-linha-de-base", action="store_true", help="baixa a linha de base depois de uma limpeza (nunca sobe)"
    )
    analisador.add_argument(
        "--sem-linha-de-base", action="store_true", help="ignora a linha de base e lista toda a dívida como falha"
    )
    analisador.add_argument("--sem-testes", action="store_true", help="não roda python -m unittest discover")
    analisador.add_argument("--raiz", help="raiz do repositório (padrão: a do diretório atual)")
    return analisador.parse_args(argv)


def verificacoes_do_modo(args):
    todas = POR_ARQUIVO + DO_REPOSITORIO
    escolhidas = NO_COMMIT if args.modo == "commit" else todas
    if args.so:
        escolhidas = [v for v in todas if v.ID in args.so]
    return [v for v in escolhidas if not (args.sem_testes and v is testes)]


def ids_desconhecidos(args):
    conhecidos = {v.ID for v in POR_ARQUIVO + DO_REPOSITORIO}
    return sorted(set(args.so) - conhecidos)


def descrever(achado):
    onde = achado.arquivo
    if achado.linha:
        onde = f"{onde}:{achado.linha}"
    return f"{onde}: {achado.detalhe}" if onde else achado.detalhe


def imprimir_falha(verificacao, achados, completo):
    print(f"✗ {verificacao.ID}: {verificacao.TITULO} ({len(achados)})")
    mostrados = achados if completo else achados[:LINHAS_POR_VERIFICACAO]
    for achado in mostrados:
        print("    " + descrever(achado).replace("\n", "\n      "))
    if len(mostrados) < len(achados):
        print(f"    ... e mais {len(achados) - len(mostrados)} (use --completo para listar todos)")
    print(f"  Conserto: {verificacao.CONSERTO}")


def verificar_com_catraca(ctx, verificacao, linha_de_base):
    achados = verificacao.verificar(ctx)
    if linha_de_base is None or verificacao.ID not in ctx.limites["linha_de_base"]["verificacoes"]:
        return achados, 0
    return catraca.aplicar(ctx, verificacao.ID, achados, linha_de_base)


def executar(ctx, verificacoes, args):
    linha_de_base = None if args.sem_linha_de_base else catraca.carregar(ctx)
    falhas = []
    for verificacao in verificacoes:
        achados, divida = verificar_com_catraca(ctx, verificacao, linha_de_base)
        if achados:
            falhas.append(verificacao)
            imprimir_falha(verificacao, achados, args.completo)
        else:
            print(f"✓ {verificacao.ID}" + (f" ({divida} na linha de base)" if divida else ""))
    return falhas


def mexer_na_linha_de_base(ctx, verificacoes, args):
    if args.modo != "tudo":
        print("--criar-linha-de-base e --atualizar-linha-de-base pedem --tudo", file=sys.stderr)
        return 2
    ratchet = ctx.limites["linha_de_base"]["verificacoes"]
    resultados = {v.ID: v.verificar(ctx) for v in verificacoes if v.ID in ratchet}
    mexer = catraca.criar if args.criar_linha_de_base else catraca.atualizar
    codigo, mensagens = mexer(ctx, resultados)
    print(chr(10).join(mensagens))
    return codigo


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = ler_argumentos(argv)
    desconhecidos = ids_desconhecidos(args)
    if desconhecidos:
        print(f"verificação desconhecida: {', '.join(desconhecidos)}", file=sys.stderr)
        return 2
    raiz = Path(args.raiz) if args.raiz else raiz_do_repositorio(Path.cwd())
    ctx = montar_contexto(raiz, args.modo, args.base)
    verificacoes = verificacoes_do_modo(args)
    if args.criar_linha_de_base or args.atualizar_linha_de_base:
        return mexer_na_linha_de_base(ctx, verificacoes, args)
    falhas = executar(ctx, verificacoes, args)
    for aviso in ctx.avisos:
        print(f"aviso: {aviso}")
    if falhas:
        print(f"\n{len(falhas)} verificação(ões) falharam: {', '.join(v.ID for v in falhas)}")
        return 1
    print("\ntudo certo")
    return 0
