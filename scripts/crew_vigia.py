import json
import os

Fail = None
crew = None

RESUMO_MINUTOS = 30
TITULO_MAXIMO = 80
RESPOSTA_MAXIMA = 1500
ACORDAM = {
    "erro": {"spawn_failed", "never_started", "not_pi", "gone"},
    "parado": {"stalled"},
    "parou": {"stopped"},
    "pedido": {"decision_needed", "question_for_chief"},
    "resposta do firstmate": {"firstmate_reply"},
    "PR pronta para revisão": {"pr_ready_review"},
    "PR pronta para merge": {"pr_ready_merge"},
    "branch mesclada": {"merged"},
}
SEM_PR = "relatório sem PR"
TEXTOS = {
    "gone": "o painel fechou",
    "spawn_failed": "não conseguiu abrir",
    "stalled": "não progride: a tela e os commits não mudam há tempo demais",
    "never_started": "o painel abriu mas o Pi nunca começou (0 turnos)",
    "merged": "a branch entrou na base",
    "report_written": "escreveu o relatório e não tem PR",
}
RESUMO = {
    "turn_ended": ("turno", "turnos"),
    "spawned": ("worker aberto", "workers abertos"),
    "closed": ("worker fechado", "workers fechados"),
    "told": ("recado", "recados"),
    "decision_answered": ("decisão respondida", "decisões respondidas"),
    "report_written": ("relatório de worker com PR ou de revisão", "relatórios de worker com PR ou de revisão"),
}
PEDIDOS = {"decision_needed", "question_for_chief"}
PRS_PRONTAS = {"pr_ready_review", "pr_ready_merge"}


def arquivo(nome):
    return os.path.join(crew.STATE, nome)


def sem_pr_esperada():
    return crew.module("crew_prs").com_pr() | {m["name"] for m in crew.workers(True) if m.get("type") == "review"}


def ciclo_de_vida(eventos):
    ultimo = {}
    for evento in eventos:
        if evento and evento["kind"] in ("spawned", "closed"):
            ultimo[evento["worker"]] = evento
    return ultimo


def pr_encerrada(evento):
    prs = crew.file_state(arquivo("prs.json")).get("prs", {})
    achada = [p for p in prs.get(evento.get("repo"), []) if p["number"] == evento.get("number")]
    return bool(achada) and (achada[0]["state"] != "OPEN" or achada[0]["head"] != evento.get("head"))


def obsoleto(evento, ciclo):
    tipo, fechado = evento["kind"], ciclo.get(evento["worker"], {})
    if tipo == "merged":
        return fechado.get("kind") == "closed"
    if tipo in PRS_PRONTAS:
        return (fechado.get("kind") == "closed" and bool(fechado.get("merged"))) or pr_encerrada(evento)
    if tipo in PEDIDOS:
        return crew.decisions().get(evento.get("id"), {}).get("status", "open") != "open"
    return False


def motivo(evento, sem_pr, ciclo):
    if obsoleto(evento, ciclo):
        return None
    for nome, tipos in ACORDAM.items():
        if evento["kind"] in tipos:
            return nome
    if evento["kind"] == "report_written" and evento["worker"] not in sem_pr:
        return SEM_PR
    return None


def titulo(evento):
    pergunta = evento.get("question") or crew.decisions().get(evento.get("id"), {}).get("question") or ""
    pergunta = " ".join(pergunta.split())
    return pergunta if len(pergunta) <= TITULO_MAXIMO else pergunta[: TITULO_MAXIMO - 1] + "…"


def texto_do_pedido(evento):
    numero = evento.get("id") or ""
    if numero.startswith("P"):
        return "%s pergunta ao chief: %s «%s»" % (evento["worker"], numero, titulo(evento))
    return "%s precisa de uma decisão: %s «%s»" % (evento["worker"], numero, titulo(evento))


def texto(evento):
    tipo = evento["kind"]
    if tipo == "not_pi":
        return "%s: o agente do painel agora é %s, não Pi (o restore do Herdr reabriu o painel; o contexto do worker se perdeu)" % (
            evento["worker"], evento.get("agent"))
    if tipo in ("decision_needed", "question_for_chief"):
        return texto_do_pedido(evento)
    if tipo == "firstmate_reply":
        return "respondeu à nota «%s»: %s" % (" ".join(evento.get("note", "").split())[:TITULO_MAXIMO], " ".join(evento.get("reply", "").split())[:RESPOSTA_MAXIMA])
    if tipo == "stopped":
        return "%s: parou, causa: %s" % (evento["worker"], evento.get("cause"))
    if tipo.startswith("pr_ready"):
        return "%s#%s «%s» (%s)" % (evento.get("repo"), evento.get("number"), evento.get("title"), evento["worker"])
    return "%s: %s" % (evento["worker"], TEXTOS.get(tipo, tipo))


def agrupar(eventos, sem_pr, ciclo):
    grupos = {}
    for evento in eventos:
        nome = motivo(evento, sem_pr, ciclo)
        if nome:
            grupos.setdefault(nome, []).append(texto(evento))
    return ["%s: %s" % (nome, "; ".join(lista)) for nome, lista in grupos.items()]


def avisar(chief, linhas):
    try:
        crew.tell_chief(chief, "[crew] aviso automático, ninguém pediu nada: %s. (O estado completo está em `python scripts/crew.py board`.)" % " | ".join(linhas))
    except OSError as e:
        print(json.dumps(dict(ok=False, step="notify", error=str(e))), flush=True)
        return False
    return True


def contar(eventos, sem_pr, ciclo):
    contas = {}
    for evento in eventos:
        if evento["kind"] in RESUMO and not motivo(evento, sem_pr, ciclo):
            contas[evento["kind"]] = contas.get(evento["kind"], 0) + 1
    return ", ".join("%d %s" % (n, RESUMO[tipo][n != 1]) for tipo, n in contas.items())


def hora(segundos):
    return crew.datetime.datetime.fromtimestamp(segundos).strftime("%H:%M")


def guardar(chief, linha):
    with open(arquivo("resumo.md"), "a", encoding="utf-8") as f:
        f.write(linha + "\n")
    try:
        crew.tell_chief(chief, "[resumo] " + linha.lstrip("- "))
    except OSError as e:
        print(json.dumps(dict(ok=False, step="resumo", error=str(e))), flush=True)


def resumir(chief, eventos, minutos, sem_pr):
    caminho = arquivo("resumo.json")
    visto = crew.file_state(caminho)
    agora = crew.time.time()
    if visto.get("n", len(eventos) + 1) > len(eventos):
        visto = dict(n=len(eventos), t=agora)
    elif agora - visto.get("t", agora) >= minutos * 60:
        contas = contar([e for e in eventos[visto["n"]:] if e], sem_pr, ciclo_de_vida(eventos))
        if contas:
            guardar(chief, "- Resumo %s–%s: %s" % (hora(visto["t"]), hora(agora), contas))
        visto = dict(n=len(eventos), t=agora)
    crew.write_text(caminho, json.dumps(visto))


def rodada(chief, minutos=RESUMO_MINUTOS):
    prs = crew.module("crew_prs")
    prs.refresh()
    crew.module("crew_firstmate").refresh()
    eventos = crew.read_events()
    avisados = crew.notice_cursor(len(eventos))
    sem_pr = sem_pr_esperada()
    linhas = agrupar([e for e in eventos[avisados:] if e], sem_pr, ciclo_de_vida(eventos))
    if linhas and not avisar(chief, linhas):
        return
    crew.write_text(crew.NOTIFIED, str(len(eventos)))
    resumir(chief, eventos, minutos, sem_pr)
