import json
import os

Fail = None
crew = None

INTERVALO = 60
ESPERA_DO_SSH = 20
RECIBOS = " receipts --all-handled --all-pending --all-replies"


def arquivo():
    return os.path.join(crew.STATE, "firstmate.json")


def ler_recibos():
    fm = crew.module("firstmate")
    codigo, saida, erro = fm.call(fm.INBOX + RECIBOS, timeout=ESPERA_DO_SSH)
    if codigo != 0:
        raise Fail("firstmate", (erro or saida).strip() or "exit %d" % codigo)
    return json.loads(saida)


def respostas(recibos, etiqueta):
    notas = {n["id"]: n for n in recibos["handled"] + recibos["pending"] if n.get("body", "").startswith(etiqueta)}
    return [dict(chave="%s:%s" % (r["id"], r.get("cursor", "")), nota=notas[r["id"]].get("body", ""), texto=r.get("body", ""))
            for r in recibos["replies"] if r["id"] in notas]


def refresh():
    anterior = crew.file_state(arquivo())
    if crew.time.time() - anterior.get("t", 0) < INTERVALO:
        return
    try:
        achadas = respostas(ler_recibos(), crew.module("firstmate").TAG)
    except (Fail, OSError, ValueError, KeyError, TypeError) as e:
        erro = str(getattr(e, "error", e))
        if erro != anterior.get("erro"):
            print(json.dumps(dict(ok=False, step="firstmate", error=erro)), flush=True)
        crew.write_text(arquivo(), json.dumps(dict(anterior, t=crew.time.time(), erro=erro)))
        return
    if "visto" in anterior:
        for resposta in achadas:
            if resposta["chave"] not in anterior["visto"]:
                crew.emit("firstmate_reply", "firstmate", note=resposta["nota"], reply=resposta["texto"])
    crew.write_text(arquivo(), json.dumps(dict(t=crew.time.time(), at=crew.now(), visto=[r["chave"] for r in achadas], erro=None)))
