import csv
import datetime
import os
import re
import subprocess
import sys

BATIDA_VELHA_SEGUNDOS = 300
SEM_CAUSA_CONHECIDA = "erro desconhecido"
PADROES = [
    ("disco", r"ENOSPC|no space left on device"),
    ("conversa quebrada no bridge", r"Cut boundary|Session boundary"),
    ("crédito", r"credit balance is too low|Plans & Billing|insufficient_quota"),
    ("limite de uso", r"quota exceeded|out of extra usage|usage limit|rate limit \("),
    ("credencial", r"authentication_error|API Key appears to be invalid|invalid x-api-key|\b401\b|Unauthorized"),
    ("recusa", r"safeguards flagged|can't respond to this message"),
    ("API fora", r"overloaded|\b(?:429|500|502|503|504|529)\b|rate limit|Service Unavailable|Bad Gateway"),
    ("rede", r"ECONNRESET|ECONNREFUSED|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|fetch failed|socket hang up|timed? ?out|network"),
]


def tasklist(pid):
    saida = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace",
                           creationflags=0x08000000)
    return saida.stdout


def vivo(pid, plataforma=sys.platform, listar=tasklist):
    if plataforma == "win32":
        return str(pid) in {linha[1] for linha in csv.reader(listar(pid).splitlines()) if len(linha) > 1}
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def instante(texto):
    try:
        return datetime.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None


def batida_velha(visto, agora):
    batida = instante(visto.get("beat"))
    return bool(batida) and (agora - batida).total_seconds() > BATIDA_VELHA_SEGUNDOS


def do_desfecho(desfecho):
    if desfecho.get("type") == "aborted":
        return "interrompido"
    texto = str(desfecho.get("message") or "")
    return next((causa for causa, padrao in PADROES if re.search(padrao, texto, re.I)), SEM_CAUSA_CONHECIDA)


def pid_do(visto):
    pid = visto.get("pid")
    return pid if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 else None


def da_parada(visto, agora=None):
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    if visto.get("state") == "gone":
        return None
    if visto.get("state") == "idle" and isinstance(visto.get("outcome"), dict):
        return do_desfecho(visto["outcome"])
    pid = pid_do(visto)
    if pid is None:
        return None
    if not vivo(pid):
        return "Pi saiu"
    return "congelado" if batida_velha(visto, agora) else None
