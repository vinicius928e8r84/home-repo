import json
import os

Fail = None
crew = None

PARAS = ("chief", "dono")
LABEL = {"chief": "Pergunta", "dono": "Decisão"}
LETTER = {"chief": "P", "dono": "D"}
NEXT = "keep working on everything that does not depend on this; the answer arrives as a [chief] message"
UNKNOWN_CHIEF = "the chief's pane is unknown because the watcher is not running; the chief learns it from `board`"


def para_of(entry):
    return entry.get("para") or "dono"


def label(entry):
    return LABEL[para_of(entry)]


def next_id(para):
    letter = LETTER[para]
    return "%s%d" % (letter, 1 + sum(1 for key in crew.decisions() if key.startswith(letter)))


def chief_pane():
    try:
        return json.loads(crew.file_text(crew.HEARTBEAT))["chief"]
    except (ValueError, KeyError, TypeError):
        return None


def wake(text):
    pane = chief_pane()
    if not pane:
        return False
    try:
        crew.tell_chief(pane, text)
    except OSError:
        return False
    return True


def register(name, repo, ask, para):
    if para not in PARAS:
        raise ValueError("para must be one of %s" % ", ".join(PARAS))
    question, recommend = ask["question"], ask.get("recommend")
    entry = dict(id=next_id(para), at=crew.now(), worker=name, repo=repo, question=question, recommend=recommend, status="open", para=para)
    crew.log_decision(entry)
    if para == "dono":
        crew.emit("decision_needed", name, id=entry["id"], question=question)
        return entry, None
    crew.emit("question_for_chief", name, id=entry["id"], question=question)
    text = "[crew] %s pergunta ao chief (%s): %s Recomendação do worker: %s. Responda com `python scripts/crew.py answer %s \"...\"`."
    return entry, wake(text % (name, entry["id"], question, recommend or "nenhuma", entry["id"]))


def ask(a):
    name = a.worker or os.environ.get("CREW_AGENT_NAME")
    if name:
        repo = crew.read_meta(name)["repo"]
    elif a.repo:
        name, repo = "chief", a.repo
    else:
        raise Fail("ask", "run this from a worker's pane, or pass --worker, or --repo for a decision of the chief's own")
    para = a.para or ("dono" if name == "chief" else "chief")
    if name == "chief" and para == "chief":
        raise Fail("ask", "the chief has no one above it but the owner: use --para dono")
    entry, woke = register(name, repo, dict(question=a.question, recommend=a.recommend), para)
    result = dict(ok=True, id=entry["id"], para=para, next=NEXT)
    if para == "chief":
        result.update(woke_chief=woke, note=None if woke else UNKNOWN_CHIEF)
    return result


def tell(a):
    pane = chief_pane()
    if not pane:
        raise Fail("tell", UNKNOWN_CHIEF)
    who = os.environ.get("CREW_AGENT_NAME") or "chief"
    if not wake("[crew] %s avisa o chief: %s" % (who, a.message)):
        raise Fail("tell", "could not write to the chief's inbox")
    crew.emit("told_chief", who, message=a.message)
    return dict(ok=True, para="chief", delivered=True, note="a notice only; to get an answer use `ask --para chief`")


def open_questions(open_entries):
    return [d for d in open_entries if para_of(d) == "chief"]


def open_for_owner(open_entries):
    return [d for d in open_entries if para_of(d) == "dono"]


def questions_lines(open_entries):
    mine = sorted(open_questions(open_entries), key=lambda d: d["at"])
    out = ["## Perguntas ao chief (%d)" % len(mine)]
    for d in mine:
        out.append("- **%s** [%s · %s] %s" % (d["id"], d["repo"], d["worker"], d["question"]))
        out.append("  - recomendação do worker: %s" % (d.get("recommend") or "nenhuma"))
        out.append("  - pedida %s. Responder: `python scripts/crew.py answer %s \"...\"`" % (crew.ago(d["at"]), d["id"]))
    return out + [""]
