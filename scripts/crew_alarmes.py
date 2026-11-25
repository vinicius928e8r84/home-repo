import hashlib
import os
import re
import subprocess

Fail = None
crew = None

BRAILLE = re.compile(r"[\u2800-\u28ff]")
CRONOMETRO = re.compile(r"^.*Elapsed.*$", re.M)
FAIXA_DE_TURNO = re.compile(r"^\u2500+ [\u2800-\u28ff] \w+ \u2500+\s*$", re.M)
ESPERA = re.compile(r"\bsleep\b|\bgh\s+pr\s+checks\b|\bgh\s+run\s+watch\b|--watch\b|\blavish", re.I)
INICIO_DE_COMANDO = " $ "


def ler_tela(meta):
    try:
        return str(crew.herdr("agent", "pane", "read", meta["pane"], "--source", "recent-unwrapped", "--lines", "40"))
    except (Fail, KeyError):
        return ""


def marca(meta, tela=None):
    topo = subprocess.run(crew.git_argv(meta) + ["rev-parse", meta["branch"]], capture_output=True, text=True).stdout.strip()
    tela = ler_tela(meta) if tela is None else tela
    return topo + chr(10) + CRONOMETRO.sub("", BRAILLE.sub("", tela))


def comando_rodando(tela):
    linhas = tela.splitlines()
    inicios = [i for i, linha in enumerate(linhas) if linha.startswith(INICIO_DE_COMANDO)]
    if not inicios:
        return ""
    bloco = []
    for linha in linhas[inicios[-1]:]:
        if not linha.strip():
            break
        bloco.append(linha.strip())
    depois = [linha.strip() for linha in linhas[inicios[-1] + len(bloco):] if linha.strip()]
    return " ".join(bloco) if depois and depois[0].startswith("Elapsed") else ""


def espera_legitima(tela):
    return bool(ESPERA.search(comando_rodando(tela)))


def sem_turno_na_tela(tela):
    return bool(tela.strip()) and not FAIXA_DE_TURNO.search(tela)


def progresso(meta, seen, tela):
    atual = hashlib.sha1(marca(meta, tela).encode("utf-8", "replace")).hexdigest()
    ultimo = crew.file_state(os.path.join(crew.STATE, meta["name"], "watch.json")).get("progress")
    if not ultimo:
        return dict(mark=atual, at=seen["at"])
    return ultimo if ultimo["mark"] == atual else dict(mark=atual, at=crew.now())


def silencio(meta, seen, progress):
    mine = [d for d in crew.decisions().values() if d.get("worker") == meta["name"]]
    if any(d.get("status") == "open" for d in mine):
        return 0
    answered = [crew.minutes_since(d["answered_at"]) for d in mine if d.get("answered_at")]
    return min([crew.minutes_since(seen["at"]), crew.minutes_since(progress["at"])] + answered)


def avaliar(meta, seen, minutos):
    tela = ler_tela(meta)
    andamento = progresso(meta, seen, tela)
    quieto = silencio(meta, seen, andamento) > minutos
    folgado = espera_legitima(tela) or (sem_turno_na_tela(tela) and os.path.exists(meta["report"]))
    return dict(progress=andamento, stalled=quieto and not folgado)


def nunca_comecou(meta, state, seen, antes, minutos):
    if seen.get("turns", 0) or antes.get("turns", 0) or antes.get("had_turn") or meta.get("error"):
        return False
    if state not in ("idle", "starting"):
        return False
    idades = [crew.minutes_since(meta.get("started"))]
    if seen.get("at"):
        idades.append(crew.minutes_since(seen["at"]))
    return min(idades) > minutos
