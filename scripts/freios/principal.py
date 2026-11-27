import argparse
import sys
from pathlib import Path

from scripts.freios import (
    autoria, binario, catraca, comentarios, dados_pessoais, depuracao, externos, funcoes, links, orcamento, segredo,
    sintaxe, skills, tamanho, testes,
)
from scripts.freios.git import montar_contexto, raiz_do_repositorio

POR_ARQUIVO = [tamanho, funcoes, comentarios, sintaxe, segredo, binario, dados_pessoais, depuracao, externos]
NO_COMMIT = [tamanho, comentarios]
DO_REPOSITORIO = [skills, links, orcamento, autoria, testes]
USO = """Os freios do repositório: tetos de tamanho, sem comentário, sintaxe, segredo, dados pessoais, print() esquecido,
skills, links, orçamento de contexto e autoria dos commits.

--commit confere o tamanho e os comentários dos arquivos que estão no commit (gancho pre-commit).
--tudo confere o índice inteiro, sem arquivo não rastreado, e os commits da branch contra --base (gancho pre-push e CI).
Tamanho, comentários, dados pessoais e print() têm como teto a medida do arquivo na main (o ponto em que a branch saiu de --base): encolher passa, crescer reprova e arquivo novo nasce dentro dos limites.
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


def verificar_com_catraca(ctx, verificacao):
    achados = verificacao.verificar(ctx)
    if achados and verificacao.ID in ctx.limites["catraca"]["verificacoes"]:
        return catraca.aplicar(ctx, verificacao, achados)
    return achados, 0


def executar(ctx, verificacoes, completo):
    falhas = []
    for verificacao in verificacoes:
        achados, divida = verificar_com_catraca(ctx, verificacao)
        if achados:
            falhas.append(verificacao)
            imprimir_falha(verificacao, achados, completo)
        else:
            print(f"✓ {verificacao.ID}" + (f" ({divida} no teto da main)" if divida else ""))
    return falhas


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
    falhas = executar(ctx, verificacoes_do_modo(args), args.completo)
    for aviso in ctx.avisos:
        print(f"aviso: {aviso}")
    if falhas:
        print(f"\n{len(falhas)} verificação(ões) falharam: {', '.join(v.ID for v in falhas)}")
        return 1
    print("\ntudo certo")
    return 0
