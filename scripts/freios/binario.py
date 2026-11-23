from pathlib import Path

from scripts.freios.contexto import Achado, casa

ID = "binario"
TITULO = "Nenhum instalador, binário, arquivo grande ou cópia de backup"
CONSERTO = (
    "Instaladores e binários (.dmg, .exe, .zip, .deb, .tgz...) ficam fora do git: gere-os no CI ou "
    "publique como release. Cópias de backup (*.bak, *.orig, *.antes-*) não entram: o git já guarda "
    "o arquivo anterior. Código entra em UTF-8, sem byte nulo."
)
TRECHO_INICIAL = 512


def _suspeito(dados):
    return any(b == 0 or b < 9 or 13 < b < 32 for b in dados[:TRECHO_INICIAL])


def _assinatura(config, dados):
    if not _suspeito(dados):
        return None
    for item in config["assinaturas_proibidas"]:
        tamanho = len(item["hex"]) // 2
        if dados[:tamanho].hex() == item["hex"]:
            return item["nome"]
    return None


def _codigo_ilegivel(ctx, caminho, dados):
    if Path(caminho).suffix.lower() not in set(ctx.limites["tamanho"]["extensoes_de_codigo"]):
        return None
    if dados[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "arquivo de código em UTF-16: o interpretador o lê de outro jeito; código entra em UTF-8"
    if b"\0" in dados[:8000]:
        return "arquivo de código com byte nulo: as regras de linha e de comentário não o leem"
    return None


def _problema(ctx, caminho, dados):
    config = ctx.limites["binario"]
    if any(casa(glob, caminho) for glob in config["lixo"]):
        return "cópia de backup, sobra de editor, log ou pasta de dependências"
    extensao = Path(caminho).suffix.lower()
    if extensao in config["extensoes_proibidas"]:
        return f"extensão {extensao}: instalador, pacote ou binário não entra no repositório"
    assinatura = _assinatura(config, dados)
    if assinatura:
        return f"o conteúdo é {assinatura}, mesmo com outro nome"
    maximo = config["megabytes_maximos"] * 1024 * 1024
    if len(dados) > maximo:
        return f"{len(dados) / 1048576:.1f} MB, acima do limite de {config['megabytes_maximos']} MB"
    return _codigo_ilegivel(ctx, caminho, dados)


def verificar(ctx):
    achados = []
    for entrada in ctx.alvos:
        if ctx.excecao(ID, entrada.caminho):
            continue
        dados = ctx.ler(entrada)
        if dados is None:
            continue
        problema = _problema(ctx, entrada.caminho, dados)
        if problema:
            achados.append(Achado(ID, entrada.caminho, problema))
    return achados
