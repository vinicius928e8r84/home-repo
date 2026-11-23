import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.freios import saida_utf8

NIVEIS = ("high", "critical")
VAZIO = "0" * 40
DESCRICAO = (
    "Roda npm audit nas travas de pacotes (package-lock.json) que a mudança tocou, no ramo e na base, e falha só por "
    "vulnerabilidade alta ou crítica que a mudança introduz (que a base não tinha). Vulnerabilidade antiga não falha. "
    "Precisa de rede para o registro do npm; se o registro não responde, falha (rode de novo)."
)


class ErroDeAuditoria(Exception):
    pass


def git(raiz, *args):
    feito = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=raiz, capture_output=True, check=False)
    if feito.returncode != 0:
        raise ErroDeAuditoria(feito.stderr.decode("utf-8", "replace").strip() or f"git {' '.join(args)} falhou")
    return feito.stdout.decode("utf-8")


def git_ou_nada(raiz, *args):
    try:
        return git(raiz, *args)
    except ErroDeAuditoria:
        return None


def resolver_base(raiz, pedida):
    ref = pedida or os.environ.get("FREIOS_BASE") or "origin/main"
    if ref == VAZIO:
        return None
    topo = git_ou_nada(raiz, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if not topo:
        raise ErroDeAuditoria(f"a base {ref} não é um commit deste repositório; use --base <ref> (no CI, fetch-depth: 0)")
    desde = git_ou_nada(raiz, "merge-base", "HEAD", topo.strip())
    if not desde:
        raise ErroDeAuditoria(f"{ref} e o HEAD não têm ancestral comum; sem ele não há como saber o que a mudança acrescentou")
    return {"ref": ref, "desde": desde.strip()}


def travas_mudadas(raiz, base):
    saida = git(raiz, "diff", "--name-status", "--no-renames", "-z", f"{base['desde']}..HEAD")
    partes = [parte for parte in saida.split("\0") if parte]
    pares = zip(partes[::2], partes[1::2], strict=True)
    return sorted(caminho for status, caminho in pares if status != "D" and Path(caminho).name == "package-lock.json")


def novas_altas(base, ramo, niveis=NIVEIS):
    def altas(relatorio):
        achados = (relatorio or {}).get("vulnerabilities") or {}
        return {nome: dados for nome, dados in achados.items() if dados.get("severity") in niveis}

    antes = altas(base)
    return [
        {
            "nome": nome,
            "severidade": dados["severity"],
            "intervalo": dados.get("range"),
            "titulos": titulos_de(dados),
        }
        for nome, dados in altas(ramo).items()
        if nome not in antes
    ]


def titulos_de(dados):
    vias = [via for via in dados.get("via") or [] if isinstance(via, dict)]
    return [via["title"] for via in vias if via.get("title")][:3]


def npm_audit(pasta):
    npm = shutil.which("npm")
    if not npm:
        raise ErroDeAuditoria("o npm não está instalado; sem ele não há como auditar")
    feito = subprocess.run(
        [npm, "audit", "--json", "--package-lock-only"],
        cwd=pasta,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    try:
        relatorio = json.loads(feito.stdout)
    except json.JSONDecodeError as erro:
        primeira = (feito.stderr.strip().splitlines() or ["sem mensagem"])[0]
        raise ErroDeAuditoria(f"o npm audit não produziu JSON em {pasta}: {primeira}") from erro
    if relatorio.get("error"):
        erro = relatorio["error"]
        raise ErroDeAuditoria(f"o npm audit falhou: {erro.get('summary') or erro.get('code')}")
    return relatorio


def gravar_projeto(destino, package_json, trava):
    Path(destino).mkdir(parents=True, exist_ok=True)
    (Path(destino) / "package.json").write_text(package_json, encoding="utf-8", newline="\n")
    (Path(destino) / "package-lock.json").write_text(trava, encoding="utf-8", newline="\n")


def arquivo_na_base(raiz, base, caminho):
    return git_ou_nada(raiz, "show", f"{base['desde']}:{caminho}")


def lado_da_base(raiz, base, trava, destino):
    pasta = str(Path(trava).parent.as_posix())
    package_json = arquivo_na_base(raiz, base, f"{pasta}/package.json".removeprefix("./"))
    antiga = arquivo_na_base(raiz, base, trava)
    if package_json is None or antiga is None:
        return None
    gravar_projeto(destino, package_json, antiga)
    return destino


def auditar_trava(raiz, base, trava, auditor):
    with tempfile.TemporaryDirectory(prefix="auditoria-") as temporario:
        pasta = Path(trava).parent
        ramo = Path(temporario) / "ramo"
        try:
            package_json = (Path(raiz) / pasta / "package.json").read_text(encoding="utf-8")
            gravar_projeto(ramo, package_json, (Path(raiz) / trava).read_text(encoding="utf-8"))
        except OSError as erro:
            raise ErroDeAuditoria(f"não consegui ler {trava} e o package.json ao lado dela: {erro}") from erro
        antes = lado_da_base(raiz, base, trava, Path(temporario) / "base")
        relatorio_da_base = auditor(str(antes)) if antes else None
        return [{**achado, "trava": trava} for achado in novas_altas(relatorio_da_base, auditor(str(ramo)))]


def mostrar(novas):
    for achado in novas:
        intervalo = f", {achado['intervalo']}" if achado["intervalo"] else ""
        print(f"✗ {achado['trava']}: {achado['nome']} ({achado['severidade']}{intervalo}) {'; '.join(achado['titulos'])}")
    print(
        "Conserto: atualize ou troque o pacote para uma versão sem a falha (npm audit mostra qual); "
        "a mudança não pode introduzir vulnerabilidade alta ou crítica."
    )


def auditar(raiz, pedida, auditor=npm_audit):
    base = resolver_base(raiz, pedida)
    if not base:
        print("aviso: sem base de comparação; nada foi auditado")
        return 0
    travas = travas_mudadas(raiz, base)
    if not travas:
        print("auditoria: nenhuma trava de pacotes mudou; nada a auditar")
        return 0
    novas = [achado for trava in travas for achado in auditar_trava(raiz, base, trava, auditor)]
    if not novas:
        print(f"auditoria ok: {', '.join(travas)} não introduz vulnerabilidade {'/'.join(NIVEIS)}")
        return 0
    mostrar(novas)
    return 1


def main(argv, auditor=npm_audit):
    analisador = argparse.ArgumentParser(prog="auditoria_npm.py", description=DESCRICAO)
    analisador.add_argument("--base", help="ref de comparação (padrão: FREIOS_BASE ou origin/main)")
    analisador.add_argument("--raiz", default=".", help="raiz do repositório (padrão: a pasta atual)")
    args = analisador.parse_args(argv)
    try:
        return auditar(str(Path(args.raiz).resolve()), args.base, auditor)
    except ErroDeAuditoria as erro:
        print(f"error: {erro}")
        return 2


if __name__ == "__main__":
    saida_utf8.configurar()
    sys.exit(main(sys.argv[1:]))
