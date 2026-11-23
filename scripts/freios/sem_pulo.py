import re
import sys
from pathlib import Path

from scripts.freios import saida_utf8

PULO = re.compile(r"^aviso: .*(?:pulado|não foram conferidos).*$", re.M)
CONSERTO = (
    "no CI nenhuma ferramenta pode ser pulada: instale as dependências antes dos freios "
    "(pip install -r scripts/freios/requirements.txt; npm ci --prefix scripts/freios) e confira a configuração."
)


def pulos(texto):
    return [achado.group(0) for achado in PULO.finditer(texto)]


def ler(caminho):
    try:
        return Path(caminho).read_text(encoding="utf-8", errors="replace"), None
    except OSError as erro:
        return "", f"não consegui ler {caminho}: {erro}"


def main(argv):
    if not argv:
        print("uso: python -m scripts.freios.sem_pulo <saida-dos-freios.txt>...")
        return 2
    achados = []
    for caminho in argv:
        texto, erro = ler(caminho)
        if erro:
            print(erro)
            return 2
        achados += [f"{caminho}: {linha}" for linha in pulos(texto)]
    if not achados:
        print("nenhuma ferramenta foi pulada")
        return 0
    print("✗ os freios pularam uma verificação:")
    for achado in achados:
        print(f"    {achado}")
    print(f"  Conserto: {CONSERTO}")
    return 1


if __name__ == "__main__":
    saida_utf8.configurar()
    sys.exit(main(sys.argv[1:]))
