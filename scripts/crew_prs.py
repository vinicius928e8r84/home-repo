import json
import os
import subprocess

Fail = None
crew = None

INTERVALO = 120
LIMITE = "60"
CAMPOS = "number,headRefName,headRefOid,isDraft,state,title,statusCheckRollup"
REGISTRO = "Registro da PR"
SEM_FALHA = {"SUCCESS", "NEUTRAL", "SKIPPED"}
CONTEXTO_PENDENTE = {"PENDING", "EXPECTED"}
AVISAM = {"espera revisão": "pr_ready_review", "pronta para merge": "pr_ready_merge"}


def arquivo():
    return os.path.join(crew.STATE, "prs.json")


def veredito_do_check(check):
    if check.get("__typename") == "StatusContext":
        bruto = check.get("state", "")
        return "rodando" if bruto in CONTEXTO_PENDENTE else "ok" if bruto == "SUCCESS" else "falhou"
    if check.get("status") != "COMPLETED":
        return "rodando"
    return "ok" if check.get("conclusion") in SEM_FALHA else "falhou"


def decidir(checks):
    vereditos = [v for _, v in checks]
    outros = [v for nome, v in checks if nome != REGISTRO]
    registro = [v for nome, v in checks if nome == REGISTRO]
    if "rodando" in vereditos:
        return "espera CI"
    if "falhou" in outros:
        return "espera conserto do CI"
    if not registro or "falhou" in registro:
        return "espera revisão"
    return "pronta para merge"


def estado(pr):
    if pr["state"] != "OPEN":
        return "mesclada" if pr["state"] == "MERGED" else "fechada"
    checks = pr.get("statusCheckRollup") or []
    if pr.get("isDraft") or not checks:
        return "espera CI"
    return decidir([(c.get("name") or c.get("context") or "", veredito_do_check(c)) for c in checks])


def resumir_pr(pr):
    return dict(number=pr["number"], branch=pr["headRefName"], head=pr["headRefOid"], title=pr.get("title", ""),
                state=pr["state"], estado=estado(pr))


def buscar(repo_path):
    try:
        saida = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", LIMITE, "--json", CAMPOS], cwd=repo_path,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail("gh", str(e)) from e
    if saida.returncode != 0:
        raise Fail("gh", (saida.stderr or saida.stdout).strip() or "exit %d" % saida.returncode)
    return json.loads(saida.stdout)


def repos_abertos():
    return {m["repo"]: m["repo_path"] for m in crew.workers() if os.path.isdir(m.get("repo_path", ""))}


def ler_repos(anterior):
    prs, erros = {}, {}
    for repo, caminho in repos_abertos().items():
        try:
            prs[repo] = [resumir_pr(p) for p in buscar(caminho)]
        except (Fail, ValueError, KeyError) as e:
            erros[repo] = str(getattr(e, "error", e))
            prs[repo] = anterior.get("prs", {}).get(repo, [])
    return prs, erros


def chave(repo, pr):
    return "%s#%d" % (repo, pr["number"])


def marca(pr):
    return "%s:%s" % (pr["head"], pr["estado"])


def novidades(anterior, prs):
    visto = anterior.get("visto", {})
    achados = []
    for repo in anterior.get("lidos", []):
        for pr in prs.get(repo, []):
            if pr["state"] == "OPEN" and pr["estado"] in AVISAM and visto.get(chave(repo, pr)) != marca(pr):
                achados.append((repo, pr))
    return achados


def lembrar(anterior, prs):
    visto = dict(anterior.get("visto", {}))
    for repo, lista in prs.items():
        for pr in lista:
            if pr["state"] == "OPEN" and pr["estado"] in AVISAM:
                visto[chave(repo, pr)] = marca(pr)
    return visto


def autores():
    return {(m["repo"], m["branch"]): m["name"] for m in crew.workers(True)}


def avisar(achados):
    nomes = autores()
    for repo, pr in achados:
        quem = nomes.get((repo, pr["branch"]), "PR #%d" % pr["number"])
        crew.emit(AVISAM[pr["estado"]], quem, repo=repo, number=pr["number"], head=pr["head"], title=pr["title"])


def refresh():
    anterior = crew.file_state(arquivo())
    if crew.time.time() - anterior.get("t", 0) < INTERVALO:
        return
    prs, erros = ler_repos(anterior)
    lidos = [repo for repo in prs if repo not in erros]
    if anterior:
        avisar(novidades(anterior, prs))
    dados = dict(t=crew.time.time(), at=crew.now(), prs=prs, visto=lembrar(anterior, prs), lidos=lidos, erros=erros)
    crew.write_text(arquivo(), json.dumps(dados, ensure_ascii=False))


def com_pr():
    prs = crew.file_state(arquivo()).get("prs", {})
    return {m["name"] for m in crew.workers(True) if any(p["branch"] == m["branch"] for p in prs.get(m["repo"], []))}
