"""crew: start, watch and talk to worker agents from the Home Repo.

Each worker is a Pi agent in its own Herdr tab, working in its own git
worktree, started with written instructions (the brief). Run this from the
chief's pane inside Herdr.

  python scripts/crew.py board                      the whole fleet: decisions waiting, running, to review
  python scripts/crew.py spawn <repo> <task> --type implement --request "..." --done "..."
  python scripts/crew.py spawn <repo> <task> --host vps ...   (the worker runs on that ssh host: scripts/crew_remote.py)
  python scripts/crew.py ask "question" --recommend "..." --para chief|dono   (a worker asks the chief or the owner)
  python scripts/crew.py answer D3 "the owner's answer"   (P3: the chief answers)
  python scripts/crew.py status
  python scripts/crew.py events
  python scripts/crew.py tell <name> "message"
  python scripts/crew.py read <name>
  python scripts/crew.py close <name>
  python scripts/crew.py watch          (spawn starts it by itself, hidden)
  python scripts/crew.py guard          (the chief's turn-end hook runs it: no worker left unwatched)

Repos come from repos.json, models from model_routing.json. Every command
prints JSON; a failure prints {"ok": false, "step": ..., "error": ...} and
exits 1.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.environ.get("CREW_STATE_DIR") or os.path.join(ROOT, "state", "crew")  # the override isolates tests
EVENTS = os.path.join(STATE, "events.jsonl")
CURSOR = os.path.join(STATE, "events.cursor")
HEARTBEAT = os.path.join(STATE, "watch.heartbeat")
DECISIONS = os.path.join(STATE, "decisions.jsonl")
NOTIFIED = os.path.join(STATE, "notify.cursor")
EXTENSION = os.path.join(ROOT, ".pi", "extensions", "crew-state.ts")
UNSTARTED_MINUTES = 4


class Fail(Exception):
    def __init__(self, step, error):
        super().__init__(error)
        self.step, self.error = step, error


class Namespace:
    def __getattr__(self, name):
        return globals()[name]


MODULES = {}


def module(name):
    if name not in MODULES:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
        spec = importlib.util.spec_from_file_location(name, path)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        loaded.Fail, loaded.crew = Fail, Namespace()
        MODULES[name] = loaded
    return MODULES[name]


def remote():
    return module("crew_remote")


def git_argv(meta):
    return remote().git_argv(meta) if meta.get("host") else ["git", "-C", meta["repo_path"]]


def worktree_present(meta):
    if meta.get("host"):
        return remote().path_exists(meta["host"], meta["worktree"], "-d")
    return os.path.isdir(meta["worktree"])


def sync_remote():
    behind_ssh = [m for m in workers() if m.get("host")]
    if behind_ssh:
        try:
            remote().sync(behind_ssh)
        except (Fail, OSError) as e:
            print("remote sync failed (%s): %s" % (getattr(e, "step", "io"), getattr(e, "error", e)), file=sys.stderr)


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def posix(path):
    return os.path.abspath(path).replace("\\", "/")


def load(name):
    path = os.environ.get("CREW_REPOS") if name == "repos.json" and os.environ.get("CREW_REPOS") else os.path.join(ROOT, name)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Fail("config", "%s: %s" % (name, e))


def run(step, cmd, cwd=None):
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise Fail(step, "%s: %s" % (cmd[0], e))
    if out.returncode != 0:
        raise Fail(step, (out.stderr or out.stdout).strip() or "exit %d" % out.returncode)
    return out.stdout


def herdr(step, *args):
    """Run a Herdr command. CREW_HERDR_SESSION targets a named session from outside it (tests)."""
    if len(args) > 2 and str(args[2]).startswith("@"):
        host, plain = remote().pane_on_host(args)
        if host:
            return remote().herdr(host, step, *plain)
    session = os.environ.get("CREW_HERDR_SESSION")
    if not session and os.environ.get("HERDR_ENV") != "1":
        raise Fail(step, "not inside a Herdr pane (HERDR_ENV is not 1): open Herdr and run the chief from a pane")
    exe = shutil.which("herdr")
    if not exe:
        raise Fail(step, "`herdr` is not on PATH")
    text = run(step, [exe] + (["--session", session] if session else []) + list(args))
    try:
        return json.loads(text)
    except ValueError:
        return text


def tell_chief(pane, text):
    folder = os.path.join(STATE, "_chief")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, re.sub(r"[^A-Za-z0-9_-]", "_", pane) + ".inbox"), "a", encoding="utf-8") as f:
        f.write(" ".join(text.split()) + "\n")


def passthrough():
    """--env flags that carry the test overrides into a tab this script opens."""
    out = []
    for key in ("CREW_STATE_DIR", "CREW_REPOS"):
        if os.environ.get(key):
            out += ["--env", "%s=%s" % (key, os.environ[key])]
    return out


CREW_WORKSPACE = "crew"


def crew_workspace():
    """The Herdr workspace the workers live in, apart from the owner's: found by label, created unfocused if missing."""
    listed = herdr("pane", "workspace", "list")
    for ws in (listed.get("result", {}).get("workspaces", []) if isinstance(listed, dict) else []):
        if ws.get("label") == CREW_WORKSPACE:
            return ws["workspace_id"]
    made = herdr("pane", "workspace", "create", "--label", CREW_WORKSPACE, "--cwd", ROOT, "--no-focus")
    ws = find(made, ("workspace_id",))
    if not ws:
        raise Fail("pane", "Herdr did not return the id of the `%s` workspace" % CREW_WORKSPACE)
    return ws


def my_pane(step):
    pane = os.environ.get("HERDR_PANE_ID")
    if not pane:
        raise Fail(step, "HERDR_PANE_ID is not set: run this from a Herdr pane")
    return pane


def find(obj, keys, allowed=None):
    """First value under any of `keys`, anywhere in a JSON reply."""
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and (allowed is None or v in allowed):
                return v
        for v in obj.values():
            r = find(v, keys, allowed)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, keys, allowed)
            if r:
                return r
    return None


def pane_info(pane):
    try:
        reply = herdr("pane", "pane", "get", pane)
    except Fail as e:
        return {} if e.step == "ssh" else None
    info = reply.get("result", {}).get("pane") if isinstance(reply, dict) else None
    return info if isinstance(info, dict) else {}


def pane_alive(pane):
    return pane_info(pane) is not None


def file_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def worker_view(meta):
    """(state, agent): the state is idle, working or gone, what the worker's own Pi last wrote unless its pane is closed;
    the agent is what Herdr detects in the pane (None when unknown)."""
    state = file_state(meta.get("state_file", "")).get("state", "starting")
    inside = os.environ.get("HERDR_ENV") == "1" or os.environ.get("CREW_HERDR_SESSION") or meta.get("host")
    agent = None
    if state != "gone" and meta.get("pane") and inside:
        info = pane_info(meta["pane"])
        if info is None:
            return "gone", None
        agent = info.get("agent") if isinstance(info.get("agent"), str) else None
    return state, agent


def worker_state(meta):
    return worker_view(meta)[0]


def send(step, pane, text):
    """Type one line into a pane and press Enter. Pi queues it when it is mid-turn."""
    herdr(step, "pane", "send-text", pane, " ".join(text.split()))
    time.sleep(0.5)
    herdr(step, "pane", "send-keys", pane, "enter")


def meta_path(name):
    return os.path.join(STATE, name, "meta.json")


def read_meta(name):
    try:
        with open(meta_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        raise Fail("lookup", "no worker named %r (see `status`)" % name)


def write_meta(meta):
    with open(meta_path(meta["name"]), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def workers(include_closed=False):
    if not os.path.isdir(STATE):
        return []
    out = []
    for name in sorted(os.listdir(STATE)):
        if os.path.isfile(meta_path(name)):
            meta = read_meta(name)
            if include_closed or not meta.get("closed"):
                out.append(meta)
    return out


def emit(kind, name, **extra):
    os.makedirs(STATE, exist_ok=True)
    event = dict(at=now(), kind=kind, worker=name, **extra)
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def route_for(task_type, model):
    routing = load("model_routing.json")
    if model:
        named = routing.get("on_request", {}).get(model)
        if named:
            return named["model"], named["thinking"]
        if not re.fullmatch(r"[\w.-]+/[\w.-]+:\w+", model):
            raise Fail("route", "--model must be an on_request name %s or provider/id:thinking" % sorted(routing.get("on_request", {})))
        spec, level = model.rsplit(":", 1)
        return spec, level
    task_type = task_type or routing.get("default")
    route = routing.get("routes", {}).get(task_type)
    if not route:
        raise Fail("route", "no route %r in model_routing.json (have %s)" % (task_type, sorted(routing.get("routes", {}))))
    return route["model"], route["thinking"]


def deliver_brief(meta, pane, wait, tries=3):
    for attempt in range(tries):
        if attempt == 1:
            herdr("prompt", "pane", "send-keys", pane, "enter")
        else:
            send("prompt", pane, "Leia o arquivo %s e siga-o." % meta["brief"])
        deadline = time.time() + wait
        while time.time() < deadline:
            seen = file_state(meta["state_file"])
            if seen.get("state") == "working" or seen.get("turns", 0) > 0:
                return attempt + 1
            time.sleep(1)
    raise Fail("prompt", "Pi did not start after %d sends of the brief (%ds each): the pane is open but idle" % (tries, wait))


def cmd_spawn(a):
    repos = load("repos.json")
    repo = repos.get(a.repo)
    if not repo:
        raise Fail("repo", "no repo %r in repos.json (have %s)" % (a.repo, sorted(repos)))
    task = re.sub(r"[^a-z0-9-]+", "-", a.task.lower()).strip("-")
    name = ("%s-%s" % (repo.get("short", a.repo.lower()), task))[:32].rstrip("-")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name):
        raise Fail("name", "cannot build a Herdr agent name from %r" % name)
    if os.path.exists(meta_path(name)) and not read_meta(name).get("closed"):
        raise Fail("name", "worker %r already exists; `close` it or pick another task name" % name)
    model, level = route_for(a.type, a.model)
    request = a.request
    if a.request_file:
        with open(a.request_file, encoding="utf-8") as f:
            request = f.read().strip()
    if not request:
        raise Fail("request", "give --request or --request-file")
    if not a.done:
        raise Fail("done", "give --done: the checkable condition that tells the worker the task is finished")
    context_block = ""
    if a.context:
        context_block = "\n## Contexto\n\nLeia antes de começar:\n\n" + "\n".join("- " + item for item in a.context) + "\n"

    host = a.host or repo.get("host")
    if host and host != "local":
        job = dict(repo=repo, name=name, task=task, model=model, level=level, request=request,
                   context_block=context_block, host=host)
        return remote().spawn(a, job)

    path = os.path.expanduser(repo["path"])
    if not os.path.isdir(os.path.join(path, ".git")):
        raise Fail("repo", "%s is missing: git clone %s %s" % (path, repo["remote"], posix(path)))
    worktree = os.path.join(os.path.expanduser("~"), "worktrees", "%s-%s" % (a.repo, task))
    if os.path.exists(worktree):
        raise Fail("worktree", "%s already exists" % posix(worktree))
    branch = repo.get("branch", "{task}").format(task=task, date=datetime.date.today().strftime("%Y%m%d"))
    base = "origin/" + repo.get("default_branch", "main")
    folder = os.path.join(STATE, name)
    meta = dict(name=name, repo=a.repo, repo_path=posix(path), task=task, type=a.type or load("model_routing.json").get("default"),
                model=model, thinking=level, worktree=posix(worktree), branch=branch, base=base,
                brief=posix(os.path.join(folder, "brief.md")), report=posix(os.path.join(folder, "report.md")),
                state_file=posix(os.path.join(folder, "state.json")), started=now(),
                request=request, done_when=a.done)
    if a.dry_run:
        return dict(ok=True, dry_run=True, **meta)

    herdr("herdr", "pane", "get", my_pane("herdr"))
    run("fetch", ["git", "-C", path, "fetch", "--quiet", "origin"])
    run("worktree", ["git", "-C", path, "worktree", "add", "-b", branch, worktree, base])
    meta["base_sha"] = run("worktree", ["git", "-C", worktree, "rev-parse", "HEAD"]).strip()
    os.makedirs(folder, exist_ok=True)
    with open(meta["brief"], "w", encoding="utf-8") as f:
        f.write(BRIEF.format(home=posix(ROOT), context_block=context_block, **meta))
    write_meta(meta)
    try:
        pane = find(herdr("pane", "tab", "create", "--workspace", crew_workspace(), "--cwd", worktree, "--label", name, "--no-focus",
                          "--env", "CREW_STATE_FILE=" + meta["state_file"], "--env", "CREW_AGENT_NAME=" + name, *passthrough()), ("pane_id",))
        if not pane:
            raise Fail("pane", "Herdr did not return a pane id")
        meta["pane"] = pane
        write_meta(meta)
        herdr("agent", "pane", "run", pane, 'pi --approve -e "%s" --model %s:%s' % (posix(EXTENSION), model, level))
        deadline = time.time() + a.start_timeout
        while file_state(meta["state_file"]).get("state") != "idle":
            if time.time() > deadline:
                screen = herdr("agent", "pane", "read", pane, "--source", "recent-unwrapped", "--lines", "15")
                tail = " | ".join(line.strip() for line in str(screen).splitlines()[-6:] if line.strip())
                raise Fail("agent", "Pi did not become ready in %ds; the pane shows: %s" % (a.start_timeout, tail))
            time.sleep(1)
        deliver_brief(meta, pane, a.prompt_timeout)
    except Fail as e:
        meta["error"] = dict(step=e.step, error=e.error)
        write_meta(meta)
        emit("spawn_failed", name, step=e.step, error=e.error)
        raise Fail(e.step, "%s (worktree %s and state kept; fix and `close %s` before retrying)" % (e.error, meta["worktree"], name))
    emit("spawned", name, repo=a.repo, type=meta["type"], model="%s:%s" % (model, level))
    if not watcher_alive():
        start_watcher(my_pane("watch"))
    return dict(ok=True, watching=True, **meta)


def minutes_since(stamp):
    try:
        then = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 0
    return (datetime.datetime.now(then.tzinfo) - then).total_seconds() / 60


OWN_COMMIT = ("commit", "cherry-pick", "revert", "am")


def has_own_commit(meta):
    out = subprocess.run(git_argv(meta) + ["log", "-g", "--format=%gs", "refs/heads/" + meta["branch"]], capture_output=True, text=True)
    entries = out.stdout.splitlines() if out.returncode == 0 else []
    return not entries or any(e.startswith(OWN_COMMIT) for e in entries)


def progress_mark(meta):
    head = subprocess.run(git_argv(meta) + ["rev-parse", meta["branch"]], capture_output=True, text=True).stdout.strip()
    try:
        screen = str(herdr("agent", "pane", "read", meta["pane"], "--source", "recent-unwrapped", "--lines", "40"))
    except (Fail, KeyError):
        screen = ""
    screen = re.sub(r"[\u2800-\u28ff]", "", screen)
    screen = re.sub(r"^.*Elapsed.*$", "", screen, flags=re.M)
    return head + chr(10) + screen


def progress_since(meta, seen):
    mark = hashlib.sha1(progress_mark(meta).encode("utf-8", "replace")).hexdigest()
    last = file_state(os.path.join(STATE, meta["name"], "watch.json")).get("progress")
    if not last:
        return dict(mark=mark, at=seen["at"])
    return last if last["mark"] == mark else dict(mark=mark, at=now())


def quiet_minutes(meta, seen, progress):
    mine = [d for d in decisions().values() if d.get("worker") == meta["name"]]
    if any(d.get("status") == "open" for d in mine):
        return 0
    answered = [minutes_since(d["answered_at"]) for d in mine if d.get("answered_at")]
    return min([minutes_since(seen["at"]), minutes_since(progress["at"])] + answered)


def snapshot(meta, fetch, stall_minutes=0, unstarted_minutes=UNSTARTED_MINUTES):
    state, agent = worker_view(meta)
    seen = file_state(meta.get("state_file", ""))
    snap = dict(state=state, turns=seen.get("turns", 0), report=os.path.exists(meta["report"]), merged=False, stalled=False,
                agent=agent, not_pi=bool(agent and agent != "pi"))
    snap["unstarted"] = bool(state in ("idle", "starting") and snap["turns"] == 0 and not meta.get("error")
                             and minutes_since(meta.get("started")) > unstarted_minutes)
    if fetch:
        subprocess.run(git_argv(meta) + ["fetch", "--quiet", "origin"], capture_output=True)
    head = subprocess.run(git_argv(meta) + ["rev-parse", meta["branch"]], capture_output=True, text=True).stdout.strip()
    if head and head != meta.get("base_sha") and has_own_commit(meta):
        merged = subprocess.run(git_argv(meta) + ["merge-base", "--is-ancestor", head, meta["base"]], capture_output=True)
        snap["merged"] = merged.returncode == 0
    if state == "working" and stall_minutes and seen.get("at"):
        snap["progress"] = progress_since(meta, seen)
        snap["stalled"] = quiet_minutes(meta, seen, snap["progress"]) > stall_minutes
    return snap


BASELINE = dict(state="starting", turns=0, report=False, merged=False, stalled=False, unstarted=False, agent=None, not_pi=False)


def decisions():
    """Every decision asked so far, folded from the append-only log: id -> record."""
    out = {}
    if os.path.exists(DECISIONS):
        with open(DECISIONS, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    out.setdefault(entry["id"], {}).update(entry)
    return out


def log_decision(entry):
    os.makedirs(STATE, exist_ok=True)
    with open(DECISIONS, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cmd_answer(a):
    entry = decisions().get(a.id.upper())
    if not entry:
        raise Fail("answer", "no decision %r (see `board`)" % a.id)
    if entry.get("status") != "open":
        raise Fail("answer", "%s was already answered: %s" % (entry["id"], entry.get("answer")))
    log_decision(dict(id=entry["id"], status="answered", answered_at=now(), answer=a.answer))
    emit("decision_answered", entry["worker"], id=entry["id"], answer=a.answer)
    if entry["worker"] == "chief":
        return dict(ok=True, id=entry["id"], worker="chief", delivered=False, note="a decision of the chief's own: act on it")
    meta = read_meta(entry["worker"])
    delivered, note = False, None
    if meta.get("closed") or worker_state(meta) == "gone":
        note = "the worker is closed; the answer is recorded but nobody is acting on it"
    else:
        send("prompt", meta["pane"], "[chief] %s %s (%s): %s" % (module("crew_conversa").label(entry), entry["id"], entry["question"], a.answer))
        delivered = True
    return dict(ok=True, id=entry["id"], worker=entry["worker"], delivered=delivered, note=note)


def ago(stamp):
    try:
        then = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "?"
    minutes = int((datetime.datetime.now(then.tzinfo) - then).total_seconds() // 60)
    if minutes < 60:
        return "há %d min" % minutes
    if minutes < 48 * 60:
        return "há %dh%02d" % (minutes // 60, minutes % 60)
    return "há %d dias" % (minutes // 1440)


def first_line(text):
    return " ".join((text or "").split())[:160]


def result_of(meta):
    """The worker's own one-line result, from its report."""
    try:
        with open(meta["report"], encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    found = re.search(r"\*\*Resultado\*\*\s*:?\s*(.+)", text) or re.search(r"Resultado\s*:\s*(.+)", text)
    return first_line(found.group(1) if found else text)


def cmd_board(a):
    ensure_watcher()
    everyone = workers(True)
    open_all = [d for d in decisions().values() if d.get("status") == "open"]
    open_decisions = module("crew_conversa").open_for_owner(open_all)
    running, review, trouble = [], [], []
    for meta in everyone:
        if meta.get("closed"):
            continue
        snap = snapshot(meta, False, 20)
        meta["_snap"], meta["_result"] = snap, result_of(meta)
        waiting = [d["id"] for d in open_all if d["worker"] == meta["name"]]
        if meta.get("error") or snap["state"] in ("gone", "starting") or snap["stalled"] or snap["not_pi"]:
            trouble.append(meta)
        elif snap["state"] == "working":
            running.append(meta)
        elif snap["report"]:
            review.append(meta)
        elif waiting:
            running.append(meta)
        else:
            trouble.append(meta)
    if a.json:
        slim = lambda m: dict(name=m["name"], repo=m["repo"], type=m["type"], task=m["task"], state=m["_snap"]["state"], result=m["_result"], report=m["report"], branch=m["branch"], merged=m["_snap"]["merged"])
        return dict(ok=True, decisions=open_decisions, questions=module("crew_conversa").open_questions(open_all), running=[slim(m) for m in running], review=[slim(m) for m in review], trouble=[slim(m) for m in trouble])

    out = ["# Frota: %s" % datetime.datetime.now().strftime("%d/%m %H:%M"), ""]
    out += module("crew_conversa").questions_lines(open_all)
    out.append("## Decisões esperando por você (%d)" % len(open_decisions))
    for d in sorted(open_decisions, key=lambda d: d["at"]):
        out.append("- **%s** [%s · %s] %s" % (d["id"], d["repo"], d["worker"], d["question"]))
        if d.get("recommend"):
            out.append("  - recomendação do worker: %s" % d["recommend"])
        out.append("  - pedida %s. Responder: `python scripts/crew.py answer %s \"...\"`" % (ago(d["at"]), d["id"]))
    out.append("")
    out.append("## Rodando agora (%d)" % len(running))
    for m in running:
        state = "trabalhando" if m["_snap"]["state"] == "working" else "parado, esperando a sua decisão"
        out.append("- **%s** [%s · %s · %s] %s, aberto %s: %s" % (m["name"], m["repo"], m["type"], m["model"].split("/")[-1], state, ago(m["started"]), first_line(m.get("request", m["task"]))))
    out.append("")
    out.append("## Prontos para você revisar (%d)" % len(review))
    for m in review:
        out.append("- **%s** [%s] %s" % (m["name"], m["repo"], m["_result"]))
        merged = "já entrou na base; pode fechar" if m["_snap"]["merged"] else "ainda não entrou na base"
        out.append("  - relatório: `%s` · branch `%s` (%s)" % (m["report"], m["branch"], merged))
    out.append("")
    if trouble:
        out.append("## Com problema (%d)" % len(trouble))
        for m in trouble:
            snap = m["_snap"]
            why = ("erro ao abrir: %s" % m["error"]["error"]) if m.get("error") else "o painel fechou sem relatório" if snap["state"] == "gone" and not snap["report"] else "o painel fechou" if snap["state"] == "gone" else "o agente do painel é %s, não Pi" % snap["agent"] if snap["not_pi"] else "o painel abriu mas o Pi nunca começou (0 turnos)" if snap["unstarted"] else "sem progresso há mais de 20 min (a tela e os commits não mudaram)" if snap["stalled"] else "parou sem relatório e sem pedir decisão"
            out.append("- **%s** [%s] %s" % (m["name"], m["repo"], why))
        out.append("")
    out.append("## Onde você parou em cada projeto")
    for repo in sorted(load("repos.json")):
        mine = [m for m in everyone if m["repo"] == repo]
        if not mine:
            out.append("- **%s**: nenhum trabalho da frota ainda." % repo)
            continue
        live = [m for m in mine if not m.get("closed")]
        done = sorted((m for m in mine if m.get("closed")), key=lambda m: m["closed"])
        pending = len([d for d in open_decisions if d["repo"] == repo])
        line = "- **%s**: %d aberto(s), %d decisão(ões) pendente(s)." % (repo, len(live), pending)
        if done:
            last = done[-1]
            line += " Último fechado: %s (%s): %s" % (last["name"], ago(last["closed"]), result_of(last) or "sem relatório")
        out.append(line)
    out.append("")
    out.append("## Cole no fim da sua mensagem ao dono")
    out.append("")
    out.append("**Suas decisões**" + ("" if open_decisions else ": nenhuma."))
    for d in sorted(open_decisions, key=lambda d: d["at"]):
        out.append("- **%s** [%s] %s" % (d["id"], d["repo"], d["question"]))
        out.append("  - Recomendação: %s" % (d.get("recommend") or "nenhuma"))
    print("\n".join(out))
    return None


def ensure_watcher():
    """Open workers with nobody watching them: start the watcher, when this runs in a Herdr pane."""
    sync_remote()
    if workers() and not watcher_alive() and os.environ.get("HERDR_PANE_ID"):
        try:
            start_watcher(my_pane("watch"))
        except Fail:
            pass


def cmd_status(a):
    ensure_watcher()
    rows = []
    for meta in workers(a.all):
        snap = dict(state="closed") if meta.get("closed") else snapshot(meta, False)
        rows.append(dict(name=meta["name"], repo=meta["repo"], host=meta.get("host"), type=meta["type"], model=meta["model"], state=snap["state"],
                         report=meta["report"] if snap.get("report") else None, merged=snap.get("merged", False),
                         branch=meta["branch"], worktree=meta["worktree"], error=meta.get("error")))
    return dict(ok=True, workers=rows)


def cmd_events(a):
    ensure_watcher()
    lines = []
    if os.path.exists(EVENTS):
        with open(EVENTS, encoding="utf-8") as f:
            lines = f.readlines()
    start = 0
    if not a.all and os.path.exists(CURSOR):
        with open(CURSOR) as f:
            start = int(f.read().strip() or 0)
    os.makedirs(STATE, exist_ok=True)
    with open(CURSOR, "w") as f:
        f.write(str(len(lines)))
    return dict(ok=True, events=[json.loads(line) for line in lines[start:]])


def cmd_tell(a):
    if a.name == "chief":
        return module("crew_conversa").tell(a)
    meta = read_meta(a.name)
    send("prompt", meta["pane"], "[chief] " + a.message)
    emit("told", meta["name"], message=a.message)
    return dict(ok=True, worker=meta["name"], state=worker_state(meta))


def cmd_read(a):
    meta = read_meta(a.name)
    text = herdr("read", "pane", "read", meta["pane"], "--source", "recent-unwrapped", "--lines", str(a.lines))
    return dict(ok=True, worker=meta["name"], state=worker_state(meta), output=text)


def drop_folder(meta, notes):
    path, root = os.path.abspath(meta["worktree"]), os.path.abspath(os.path.join(os.path.expanduser("~"), "worktrees"))
    try:
        inside = path != root and os.path.commonpath([path, root]) == root
    except ValueError:
        inside = False
    if not inside:
        notes.append("pasta %s fica onde está: fora de %s" % (posix(path), posix(root)))
        return

    def writable(func, target, _exc):
        os.chmod(target, 0o700)
        func(target)

    try:
        shutil.rmtree(path, onerror=writable)
    except OSError:
        pass
    subprocess.run(["git", "-C", meta["repo_path"], "worktree", "prune"], capture_output=True)
    if os.path.exists(path):
        notes.append("pasta %s presa (algo a mantém aberta): apague à mão" % posix(path))


def cmd_close(a):
    meta = read_meta(a.name)
    snap = snapshot(meta, True)
    if not snap["merged"] and not a.force:
        raise Fail("close", "branch %s is not merged into %s; merge it first or pass --force to drop the worktree anyway" % (meta["branch"], meta["base"]))
    meta["closing"] = now()
    write_meta(meta)
    notes = []
    if meta.get("pane"):
        try:
            herdr("pane", "pane", "close", meta["pane"])
        except Fail as e:
            notes.append("pane: " + e.error)
    if worktree_present(meta):
        cmd = git_argv(meta) + ["worktree", "remove", meta["worktree"]] + (["--force"] if a.force else [])
        try:
            run("worktree", cmd)
        except Fail as e:
            if not a.force or meta.get("host"):
                raise
            notes.append("worktree: " + e.error)
            drop_folder(meta, notes)
    meta["closed"] = now()
    write_meta(meta)
    emit("closed", meta["name"], merged=snap["merged"])
    return dict(ok=True, worker=meta["name"], merged=snap["merged"], branch_kept=meta["branch"], notes=notes)


def file_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


BRIEF = file_text(os.path.join(ROOT, "scripts", "crew-brief.md")) + "\n"


def write_text(path, text):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_events():
    out = []
    if os.path.exists(EVENTS):
        with open(EVENTS, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    out.append(None)
    return out


def notice_cursor(total):
    raw = file_text(NOTIFIED)
    if not raw.isdigit() or int(raw) > total:
        write_text(NOTIFIED, str(total))
        return total
    return int(raw)


def watcher_alive():
    return os.path.exists(HEARTBEAT) and time.time() - os.path.getmtime(HEARTBEAT) < 90


def start_watcher(chief, every=20, stall=20):
    """Start the watch loop as a hidden background process; it inherits this pane's Herdr environment."""
    os.makedirs(STATE, exist_ok=True)
    log = open(os.path.join(STATE, "watch.log"), "a", encoding="utf-8")
    cmd = [sys.executable, os.path.abspath(__file__), "watch", "--chief", chief, "--every", str(every), "--stall", str(stall)]
    extra = dict(creationflags=0x08000000 | 0x00000200) if os.name == "nt" else dict(start_new_session=True)
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **extra)
    except OSError as e:
        raise Fail("watch", "could not start the watcher: %s" % e)
    return proc.pid


def cmd_watch(a):
    if not a.chief:
        chief = my_pane("watch")
        if watcher_alive():
            return dict(ok=True, already_running=True, chief=chief)
        return dict(ok=True, watcher_pid=start_watcher(chief, a.every, a.stall), chief=chief, log=posix(os.path.join(STATE, "watch.log")))
    chief = a.chief
    herdr("herdr", "pane", "get", chief)
    loops, quiet_since = 0, time.time()
    notice_cursor(len(read_events()))
    print(json.dumps(dict(ok=True, watching=True, chief=chief, every=a.every, stall_minutes=a.stall)), flush=True)
    while True:
        os.makedirs(STATE, exist_ok=True)
        with open(HEARTBEAT, "w") as f:
            f.write(json.dumps(dict(at=now(), pid=os.getpid(), chief=chief)))
        if not pane_alive(chief):
            print(json.dumps(dict(ok=True, stopped="the chief's pane is gone")), flush=True)
            os.remove(HEARTBEAT)
            return dict(ok=True, stopped="chief gone")
        sync_remote()
        open_workers = workers()
        if open_workers:
            quiet_since = time.time()
        elif time.time() - quiet_since > 600:
            os.remove(HEARTBEAT)
            return dict(ok=True, stopped="no open workers for 10 minutes")
        for meta in open_workers:
            name = meta["name"]
            seen_file = os.path.join(STATE, name, "watch.json")
            old = dict(BASELINE, **file_state(seen_file))
            snap = snapshot(meta, loops % 15 == 0, a.stall, a.unstarted)
            new = []
            if snap["turns"] > old["turns"]:
                new.append(emit("turn_ended", name, turns=snap["turns"]))
            if snap["state"] == "gone" and old["state"] != "gone" and not read_meta(name).get("closing"):
                new.append(emit("gone", name))
            if snap["report"] and not old["report"]:
                new.append(emit("report_written", name, report=meta["report"]))
            if snap["merged"] and not old["merged"]:
                new.append(emit("merged", name, branch=meta["branch"]))
            if snap["stalled"] and not old["stalled"]:
                new.append(emit("stalled", name, minutes=a.stall))
            if snap["not_pi"] and not old["not_pi"]:
                new.append(emit("not_pi", name, agent=snap["agent"]))
            if snap["unstarted"] and not old["unstarted"]:
                new.append(emit("never_started", name, minutes=a.unstarted))
            write_text(seen_file, json.dumps(snap))
            for event in new:
                print(json.dumps(event, ensure_ascii=False), flush=True)
        module("crew_vigia").rodada(chief, getattr(a, "resumo", 30))
        loops += 1
        if a.rounds and loops >= a.rounds:
            return dict(ok=True, rounds=loops)
        time.sleep(a.every)


def cmd_guard(a):
    if not workers() or watcher_alive():
        return dict(ok=True, revived=False)
    start_watcher(my_pane("guard"))
    deadline = time.time() + a.wait
    while not watcher_alive():
        if time.time() > deadline:
            raise Fail("guard", "the watcher was started but wrote no heartbeat in %ds; see %s" % (a.wait, posix(os.path.join(STATE, "watch.log"))))
        time.sleep(0.5)
    return dict(ok=True, revived=True)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spawn", help="start a worker: worktree, brief, pane, agent")
    s.add_argument("repo", help="a key of repos.json")
    s.add_argument("task", help="short task name, used in the worker, worktree and branch names")
    s.add_argument("--type", help="a route of model_routing.json (default: its `default`)")
    s.add_argument("--model", help="override: an on_request name (e.g. fable) or provider/id:thinking")
    s.add_argument("--request", help="what the worker must do, in the owner's own words")
    s.add_argument("--request-file", help="file holding the request")
    s.add_argument("--done", help="the checkable condition that makes the task finished (required)")
    s.add_argument("--context", action="append", help="a file, issue or commit the worker must read first; repeatable")
    s.add_argument("--host", help="ssh host to run the worker on (default: the repo's `host` in repos.json; `local` forces this machine)")
    s.add_argument("--start-timeout", type=int, default=90, help="seconds to wait for Pi to be ready")
    s.add_argument("--prompt-timeout", type=int, default=20, help="seconds to wait, after each send, for Pi to start on the brief")
    s.add_argument("--dry-run", action="store_true", help="print the plan; create nothing")
    s.set_defaults(fn=cmd_spawn)
    s = sub.add_parser("board", help="the whole fleet in one view: decisions waiting for the owner, running, ready to review, where each repo stopped")
    s.add_argument("--json", action="store_true", help="machine-readable instead of the text board")
    s.set_defaults(fn=cmd_board)
    s = sub.add_parser("ask", help="a worker asks the chief (default) or records a decision for the owner (--para dono), and keeps working")
    s.add_argument("question")
    s.add_argument("--recommend", required=True, help="what the worker would do, and why")
    s.add_argument("--para", choices=("chief", "dono"), help="who answers: chief (default) or dono; the chief's own asks are dono")
    s.add_argument("--worker", help="default: this pane's worker")
    s.add_argument("--repo", help="for a decision the chief itself needs, with no worker: the repo (or `geral`) it is about")
    s.set_defaults(fn=lambda a: module("crew_conversa").ask(a))
    s = sub.add_parser("answer", help="record the owner's answer to a decision and deliver it to the worker")
    s.add_argument("id")
    s.add_argument("answer")
    s.set_defaults(fn=cmd_answer)
    s = sub.add_parser("status", help="every open worker, with live state, report and merge")
    s.add_argument("--all", action="store_true", help="include closed workers")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("events", help="what changed since the last call")
    s.add_argument("--all", action="store_true", help="the whole log")
    s.set_defaults(fn=cmd_events)
    s = sub.add_parser("tell", help="send a message to a worker as a prompt, mid-run included; `tell chief` goes to the chief's inbox")
    s.add_argument("name")
    s.add_argument("message")
    s.set_defaults(fn=cmd_tell)
    s = sub.add_parser("read", help="a worker's recent terminal output")
    s.add_argument("name")
    s.add_argument("--lines", type=int, default=80)
    s.set_defaults(fn=cmd_read)
    s = sub.add_parser("close", help="close the pane and remove the worktree of a merged worker")
    s.add_argument("name")
    s.add_argument("--force", action="store_true", help="close an unmerged worker, or one whose worktree git cannot remove (the folder is deleted if it is inside ~/worktrees); its branch is kept")
    s.set_defaults(fn=cmd_close)
    s = sub.add_parser("watch", help="the hidden background watcher: logs what happens and wakes the chief only for errors, stalls, requests, PRs ready for review or merge and merged branches; the rest goes to state/crew/resumo.md. spawn starts it")
    s.add_argument("--chief", help="pane to notify; given, the watch loop runs in this process")
    s.add_argument("--every", type=int, default=20, help="seconds between checks")
    s.add_argument("--stall", type=int, default=20, help="minutes without progress (same screen, same commits) before a working worker counts as stalled")
    s.add_argument("--resumo", type=int, default=30, help="minutes between lines of state/crew/resumo.md (what did not wake the chief)")
    s.add_argument("--unstarted", type=int, default=UNSTARTED_MINUTES, help="minutes a worker may sit at 0 turns before it counts as never started")
    s.add_argument("--rounds", type=int, default=0, help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_watch)
    s = sub.add_parser("guard", help="restart the watcher when a worker is open and it is dead; the chief's turn-end hook runs this")
    s.add_argument("--wait", type=int, default=15, help="seconds to wait for the restarted watcher's first heartbeat")
    s.set_defaults(fn=cmd_guard)
    a = p.parse_args()
    try:
        result = a.fn(a)
        if result is not None:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except Fail as e:
        print(json.dumps(dict(ok=False, step=e.step, error=e.error), indent=2, ensure_ascii=False))
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
