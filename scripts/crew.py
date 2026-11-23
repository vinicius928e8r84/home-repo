"""crew: start, watch and talk to worker agents from the Home Repo.

Each worker is a Pi agent in its own Herdr tab, working in its own git
worktree, started with written instructions (the brief). Run this from the
chief's pane inside Herdr.

  python scripts/crew.py spawn <repo> <task> --type implement --request "..."
  python scripts/crew.py status
  python scripts/crew.py events
  python scripts/crew.py tell <name> "message"
  python scripts/crew.py read <name>
  python scripts/crew.py close <name>
  python scripts/crew.py watch          (opens the watcher tab)

Repos come from repos.json, models from model_routing.json. Every command
prints JSON; a failure prints {"ok": false, "step": ..., "error": ...} and
exits 1.
"""
import argparse
import datetime
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
EXTENSION = os.path.join(ROOT, ".pi", "extensions", "crew-state.ts")
CHIEF_STATE = os.path.join(STATE, "_chief", "state.json")


class Fail(Exception):
    def __init__(self, step, error):
        super().__init__(error)
        self.step, self.error = step, error


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


def passthrough():
    """--env flags that carry the test overrides into a tab this script opens."""
    out = []
    for key in ("CREW_STATE_DIR", "CREW_REPOS"):
        if os.environ.get(key):
            out += ["--env", "%s=%s" % (key, os.environ[key])]
    return out


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


def pane_alive(pane):
    try:
        herdr("pane", "pane", "get", pane)
        return True
    except Fail:
        return False


def file_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def worker_state(meta):
    """idle, working or gone: what the worker's own Pi last wrote, unless its pane is closed."""
    state = file_state(meta.get("state_file", "")).get("state", "starting")
    if state != "gone" and meta.get("pane") and not pane_alive(meta["pane"]):
        return "gone"
    return state


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


BRIEF = """# Tarefa: {task} ({type})

Você é um agente de trabalho aberto pelo orquestrador do Home Repo.

## Pedido

{request}

## Onde você trabalha

- Pasta: `{worktree}` (um worktree só seu do repo {repo}). Trabalhe só dentro dela.
- Branch: `{branch}`, criada a partir de `{base}`.
- Leia o `AGENTS.md` desta pasta antes de qualquer outra coisa e siga-o.
- Skills: os do repo ficam em `.claude/skills/` e `.agents/skills/` desta pasta; os gerais em `{home}/.agents/skills/`. Leia o `SKILL.md` do que a tarefa pedir, como arquivo.

## Regras

- Faça commits pequenos nesta branch. Push, merge e PR só se o pedido mandar.
- Uma mensagem que começa com `[chief]` vem do orquestrador: ela tem prioridade sobre o que você está fazendo.
- Decisão que cabe ao dono (escopo, gasto, algo irreversível): pare e avise, em vez de escolher por ele.

## Como avisar

Ao terminar, ou ao travar, escreva `{report}` com:

- **Resultado**: feito, parcial ou bloqueado, em uma linha.
- **O que mudou**: os commits, com o hash.
- **Como verificou**: o comando rodado e o que ele mostrou.
- **Pendências**: perguntas e o que ficou de fora.

Depois de escrever o arquivo, pare e espere. O orquestrador é avisado sozinho.
"""


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
                state_file=posix(os.path.join(folder, "state.json")), started=now())
    if a.dry_run:
        return dict(ok=True, dry_run=True, **meta)

    herdr("herdr", "pane", "get", my_pane("herdr"))
    run("fetch", ["git", "-C", path, "fetch", "--quiet", "origin"])
    run("worktree", ["git", "-C", path, "worktree", "add", "-b", branch, worktree, base])
    meta["base_sha"] = run("worktree", ["git", "-C", worktree, "rev-parse", "HEAD"]).strip()
    os.makedirs(folder, exist_ok=True)
    with open(meta["brief"], "w", encoding="utf-8") as f:
        f.write(BRIEF.format(request=request, home=posix(ROOT), **meta))
    write_meta(meta)
    try:
        pane = find(herdr("pane", "tab", "create", "--workspace", my_pane("pane").split(":")[0], "--cwd", worktree, "--label", name, "--no-focus",
                          "--env", "CREW_STATE_FILE=" + meta["state_file"], "--env", "CREW_AGENT_NAME=" + name, *passthrough()), ("pane_id",))
        if not pane:
            raise Fail("pane", "Herdr did not return a pane id")
        meta["pane"] = pane
        write_meta(meta)
        herdr("agent", "pane", "run", pane, 'pi -e "%s" --model %s:%s' % (posix(EXTENSION), model, level))
        deadline = time.time() + a.start_timeout
        while file_state(meta["state_file"]).get("state") != "idle":
            if time.time() > deadline:
                screen = herdr("agent", "pane", "read", pane, "--source", "recent-unwrapped", "--lines", "15")
                tail = " | ".join(line.strip() for line in str(screen).splitlines()[-6:] if line.strip())
                raise Fail("agent", "Pi did not become ready in %ds; the pane shows: %s" % (a.start_timeout, tail))
            time.sleep(1)
        send("prompt", pane, "Leia o arquivo %s e siga-o." % meta["brief"])
    except Fail as e:
        meta["error"] = dict(step=e.step, error=e.error)
        write_meta(meta)
        emit("spawn_failed", name, step=e.step, error=e.error)
        raise Fail(e.step, "%s (worktree %s and state kept; fix and `close %s` before retrying)" % (e.error, meta["worktree"], name))
    emit("spawned", name, repo=a.repo, type=meta["type"], model="%s:%s" % (model, level))
    watching = os.path.exists(HEARTBEAT) and time.time() - os.path.getmtime(HEARTBEAT) < 120
    return dict(ok=True, watching=watching, hint=None if watching else "no watcher running: run `python scripts/crew.py watch`", **meta)


def snapshot(meta, fetch, stall_minutes=0):
    state = worker_state(meta)
    seen = file_state(meta.get("state_file", ""))
    snap = dict(state=state, turns=seen.get("turns", 0), report=os.path.exists(meta["report"]), merged=False, stalled=False)
    if fetch:
        subprocess.run(["git", "-C", meta["repo_path"], "fetch", "--quiet", "origin"], capture_output=True)
    head = subprocess.run(["git", "-C", meta["repo_path"], "rev-parse", meta["branch"]], capture_output=True, text=True).stdout.strip()
    if head and head != meta.get("base_sha"):
        merged = subprocess.run(["git", "-C", meta["repo_path"], "merge-base", "--is-ancestor", head, meta["base"]], capture_output=True)
        snap["merged"] = merged.returncode == 0
    if state == "working" and stall_minutes and seen.get("at"):
        since = datetime.datetime.fromisoformat(seen["at"].replace("Z", "+00:00"))
        snap["stalled"] = (datetime.datetime.now(datetime.timezone.utc) - since).total_seconds() > stall_minutes * 60
    return snap


BASELINE = dict(state="starting", turns=0, report=False, merged=False, stalled=False)


def cmd_status(a):
    rows = []
    for meta in workers(a.all):
        snap = dict(state="closed") if meta.get("closed") else snapshot(meta, False)
        rows.append(dict(name=meta["name"], repo=meta["repo"], type=meta["type"], model=meta["model"], state=snap["state"],
                         report=meta["report"] if snap.get("report") else None, merged=snap.get("merged", False),
                         branch=meta["branch"], worktree=meta["worktree"], error=meta.get("error")))
    return dict(ok=True, workers=rows)


def cmd_events(a):
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
    meta = read_meta(a.name)
    send("prompt", meta["pane"], "[chief] " + a.message)
    emit("told", meta["name"], message=a.message)
    return dict(ok=True, worker=meta["name"], state=worker_state(meta))


def cmd_read(a):
    meta = read_meta(a.name)
    text = herdr("read", "pane", "read", meta["pane"], "--source", "recent-unwrapped", "--lines", str(a.lines))
    return dict(ok=True, worker=meta["name"], state=worker_state(meta), output=text)


def cmd_close(a):
    meta = read_meta(a.name)
    snap = snapshot(meta, True)
    if not snap["merged"] and not a.force:
        raise Fail("close", "branch %s is not merged into %s; merge it first or pass --force to drop the worktree anyway" % (meta["branch"], meta["base"]))
    notes = []
    if meta.get("pane"):
        try:
            herdr("pane", "pane", "close", meta["pane"])
        except Fail as e:
            notes.append("pane: " + e.error)
    if os.path.isdir(meta["worktree"]):
        cmd = ["git", "-C", meta["repo_path"], "worktree", "remove", meta["worktree"]] + (["--force"] if a.force else [])
        run("worktree", cmd)
    meta["closed"] = now()
    write_meta(meta)
    emit("closed", meta["name"], merged=snap["merged"])
    return dict(ok=True, worker=meta["name"], merged=snap["merged"], branch_kept=meta["branch"], notes=notes)


def describe(event):
    text = {"turn_ended": "terminou um turno", "gone": "o painel fechou",
            "report_written": "escreveu o relatório", "merged": "a branch entrou na base", "stalled": "está no mesmo turno há tempo demais"}
    return "%s: %s" % (event["worker"], text.get(event["kind"], event["kind"]))


def cmd_watch(a):
    if not a.chief:
        chief = my_pane("watch")
        pane = find(herdr("pane", "tab", "create", "--workspace", chief.split(":")[0], "--cwd", ROOT, "--label", "crew-watch", "--no-focus", *passthrough()), ("pane_id",))
        if not pane:
            raise Fail("watch", "Herdr did not return a pane id for the watcher")
        herdr("watch", "pane", "run", pane, "python scripts/crew.py watch --chief %s --every %d --stall %d" % (chief, a.every, a.stall))
        return dict(ok=True, watcher_pane=pane, chief=chief)
    chief = a.chief
    herdr("herdr", "pane", "get", chief)
    pending, loops = [], 0
    print(json.dumps(dict(ok=True, watching=True, chief=chief, every=a.every, stall_minutes=a.stall)), flush=True)
    while True:
        os.makedirs(STATE, exist_ok=True)
        with open(HEARTBEAT, "w") as f:
            f.write(now())
        for meta in workers():
            name = meta["name"]
            seen_file = os.path.join(STATE, name, "watch.json")
            old = dict(BASELINE, **file_state(seen_file))
            snap = snapshot(meta, loops % 15 == 0, a.stall)
            new = []
            if snap["turns"] > old["turns"]:
                new.append(emit("turn_ended", name, turns=snap["turns"]))
            if snap["state"] == "gone" and old["state"] != "gone":
                new.append(emit("gone", name))
            if snap["report"] and not old["report"]:
                new.append(emit("report_written", name, report=meta["report"]))
            if snap["merged"] and not old["merged"]:
                new.append(emit("merged", name, branch=meta["branch"]))
            if snap["stalled"] and not old["stalled"]:
                new.append(emit("stalled", name, minutes=a.stall))
            with open(seen_file, "w", encoding="utf-8") as f:
                json.dump(snap, f)
            pending.extend(new)
            for event in new:
                print(json.dumps(event, ensure_ascii=False), flush=True)
        if pending and file_state(CHIEF_STATE).get("state") == "idle":
            try:
                send("notify", chief, "[crew] %s. Rode `python scripts/crew.py events` e avise o dono do que importa." % "; ".join(describe(e) for e in pending))
                pending = []
            except Fail as e:
                print(json.dumps(dict(ok=False, step=e.step, error=e.error)), flush=True)
        loops += 1
        if a.rounds and loops >= a.rounds:
            return dict(ok=True, rounds=loops, pending=len(pending))
        time.sleep(a.every)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spawn", help="start a worker: worktree, brief, pane, agent")
    s.add_argument("repo", help="a key of repos.json")
    s.add_argument("task", help="short task name, used in the worker, worktree and branch names")
    s.add_argument("--type", help="a route of model_routing.json (default: its `default`)")
    s.add_argument("--model", help="override: an on_request name (e.g. fable) or provider/id:thinking")
    s.add_argument("--request", help="what the worker must do")
    s.add_argument("--request-file", help="file holding the request")
    s.add_argument("--start-timeout", type=int, default=90, help="seconds to wait for Pi to be ready")
    s.add_argument("--dry-run", action="store_true", help="print the plan; create nothing")
    s.set_defaults(fn=cmd_spawn)
    s = sub.add_parser("status", help="every open worker, with live state, report and merge")
    s.add_argument("--all", action="store_true", help="include closed workers")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("events", help="what changed since the last call")
    s.add_argument("--all", action="store_true", help="the whole log")
    s.set_defaults(fn=cmd_events)
    s = sub.add_parser("tell", help="send a message to a worker as a prompt, mid-run included")
    s.add_argument("name")
    s.add_argument("message")
    s.set_defaults(fn=cmd_tell)
    s = sub.add_parser("read", help="a worker's recent terminal output")
    s.add_argument("name")
    s.add_argument("--lines", type=int, default=80)
    s.set_defaults(fn=cmd_read)
    s = sub.add_parser("close", help="close the pane and remove the worktree of a merged worker")
    s.add_argument("name")
    s.add_argument("--force", action="store_true", help="close an unmerged worker; its branch is kept")
    s.set_defaults(fn=cmd_close)
    s = sub.add_parser("watch", help="from the chief's pane: open the watcher pane, which logs turn ends, blocks, reports, merges and stalls and tells the chief")
    s.add_argument("--chief", help="pane to notify; given, the watch loop runs here instead of opening a pane")
    s.add_argument("--every", type=int, default=20, help="seconds between checks")
    s.add_argument("--stall", type=int, default=20, help="minutes one turn may run before it counts as stalled")
    s.add_argument("--rounds", type=int, default=0, help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_watch)
    a = p.parse_args()
    try:
        print(json.dumps(a.fn(a), indent=2, ensure_ascii=False))
    except Fail as e:
        print(json.dumps(dict(ok=False, step=e.step, error=e.error), indent=2, ensure_ascii=False))
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


main()
