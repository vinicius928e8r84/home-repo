import datetime
import json
import os
import re
import shlex
import subprocess
import time

Fail = None
crew = None

SESSION = os.environ.get("CREW_REMOTE_SESSION", "crew")
CREW_HOME = os.environ.get("CREW_REMOTE_HOME", "$HOME/.local/share/crew")
STATE_DIR = os.environ.get("CREW_REMOTE_DIR", "$HOME/crew-state")
GIT_TIMEOUT = os.environ.get("CREW_REMOTE_GIT_TIMEOUT", "120")
PANE_ON_HOST = re.compile(r"@([A-Za-z0-9_.@-]+):(\S+)")
PANE_VERBS = {"get", "run", "read", "send-text", "send-keys", "close"}
ASK_COMMAND = re.compile(r'python3? "[^"]*crew\.py" ask')

ASK_SCRIPT = '''import argparse
import datetime
import json
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument("question")
parser.add_argument("--recommend", required=True)
parser.add_argument("--para", choices=["chief", "dono"], default="chief")
args = parser.parse_args()
state_file = os.environ.get("CREW_STATE_FILE")
if not state_file:
    print(json.dumps(dict(ok=False, step="ask", error="CREW_STATE_FILE is not set: run this from the worker's own pane")))
    sys.exit(1)
entry = dict(at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"), question=args.question, recommend=args.recommend, para=args.para)
with open(os.path.join(os.path.dirname(state_file), "asks.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\\n")
print(json.dumps(dict(ok=True, next="keep working on everything that does not depend on this; the answer arrives as a [chief] message")))
'''

PULL_SCRIPT = '''import json
import os
import sys

out = {}
for folder in sys.argv[1:]:
    item = {}
    for key, name in (("state", "state.json"), ("report", "report.md"), ("asks", "asks.jsonl")):
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                item[key] = f.read()
        except OSError:
            item[key] = None
    out[folder] = item
print(json.dumps(out))
'''


def ssh_argv(host, *extra):
    custom = os.environ.get("CREW_SSH")
    base = json.loads(custom) if custom and custom.startswith("[") else [custom or "ssh"]
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3"]
    return base + options + list(extra) + [host]


def ssh(host, command, step="remote", stdin=None):
    kwargs = dict(input=stdin.encode("utf-8")) if stdin is not None else dict(stdin=subprocess.DEVNULL)
    try:
        out = subprocess.run(ssh_argv(host) + [command], capture_output=True, timeout=180, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail("ssh", "cannot run ssh to %s: %s" % (host, e)) from e
    text = out.stdout.decode("utf-8", "replace")
    error = out.stderr.decode("utf-8", "replace").strip()
    if out.returncode == 255:
        raise Fail("ssh", "cannot reach %s: %s" % (host, error or "ssh exit 255"))
    if out.returncode != 0:
        raise Fail(step, error or text.strip() or "exit %d on %s" % (out.returncode, host))
    return text


def pane_on_host(args):
    args = list(args)
    if len(args) > 2 and args[0] == "pane" and args[1] in PANE_VERBS:
        found = PANE_ON_HOST.fullmatch(str(args[2]))
        if found:
            args[2] = found.group(2)
            return found.group(1), args
    return None, args


def herdr(host, step, *args):
    command = " ".join(['"%s/bin/herdr"' % CREW_HOME, "--session", shlex.quote(SESSION)] + [shlex.quote(str(a)) for a in args])
    text = ssh(host, command, step)
    try:
        return json.loads(text)
    except ValueError:
        return text


def git_argv(meta):
    return ssh_argv(meta["host"], "-n") + ["timeout", GIT_TIMEOUT, "git", "-C", shlex.quote(meta["repo_path"])]


def path_exists(host, path, flag="-e"):
    try:
        ssh(host, "test %s %s" % (flag, shlex.quote(path)))
        return True
    except Fail as e:
        if e.step == "ssh":
            raise
        return False


def put(host, path, text):
    ssh(host, "mkdir -p %s && cat > %s" % (shlex.quote(os.path.dirname(path)), shlex.quote(path)), "upload", stdin=text)


def absolute(path, home):
    for prefix in ("$HOME", "~"):
        if path == prefix or path.startswith(prefix + "/"):
            return home + path[len(prefix):]
    return path


def mirror(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".part"
    with open(temp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(temp, path)


def register_ask(meta, line):
    ask = json.loads(line)
    crew.module("crew_conversa").register(meta["name"], meta["repo"], dict(question=ask["question"], recommend=ask.get("recommend")), ask.get("para", "dono"))


def register_asks(meta, text):
    lines = [line for line in (text or "").rpartition("\n")[0].splitlines() if line.strip()]
    seen_path = os.path.join(crew.STATE, meta["name"], "asks.seen")
    seen = int(crew.file_text(seen_path) or 0)
    broken = []
    for number, line in enumerate(lines[seen:], seen + 1):
        try:
            register_ask(meta, line)
        except (ValueError, KeyError, TypeError, AttributeError):
            broken.append(line[:80])
        crew.write_text(seen_path, str(number))
    if broken:
        raise Fail("sync", "%s: asks.jsonl on %s has %d line(s) that are not a decision and were skipped: %r" % (meta["name"], meta["host"], len(broken), broken))


def pull(host, group):
    folders = " ".join(shlex.quote(m["remote_dir"]) for m in group)
    pulled = json.loads(ssh(host, "python3 - " + folders, "sync", stdin=PULL_SCRIPT))
    if not isinstance(pulled, dict):
        raise ValueError("not an object")
    return pulled


def mirror_worker(meta, item):
    if item.get("state") is not None:
        mirror(meta["state_file"], item["state"])
    if item.get("report") is not None:
        mirror(meta["report"], item["report"])
    register_asks(meta, item.get("asks"))


def sync_host(host, group):
    try:
        pulled = pull(host, group)
    except ValueError as e:
        return ["%s answered something that is not the state of its workers (%s)" % (host, e)]
    except Fail as e:
        return ["%s: %s" % (host, e.error)]
    problems = []
    for meta in group:
        try:
            mirror_worker(meta, pulled.get(meta["remote_dir"], {}))
        except Fail as e:
            problems.append(e.error)
    return problems


def sync(metas):
    by_host = {}
    for meta in metas:
        by_host.setdefault(meta["host"], []).append(meta)
    problems = [problem for host, group in by_host.items() for problem in sync_host(host, group)]
    if problems:
        raise Fail("sync", "; ".join(problems))


def describe(a, job, home):
    repo, task = job["repo"], job["task"]
    remote_dir = absolute(STATE_DIR, home) + "/" + job["name"]
    folder = os.path.join(crew.STATE, job["name"])
    return dict(name=job["name"], repo=a.repo, host=job["host"], repo_path=absolute(repo["path"], home), task=task,
                type=a.type or crew.load("model_routing.json").get("default"), model=job["model"], thinking=job["level"],
                worktree="%s/worktrees/%s-%s" % (home, a.repo, task),
                branch=repo.get("branch", "{task}").format(task=task, date=datetime.date.today().strftime("%Y%m%d")),
                base="origin/" + repo.get("default_branch", "main"), brief=remote_dir + "/brief.md",
                report=crew.posix(os.path.join(folder, "report.md")), remote_report=remote_dir + "/report.md",
                state_file=crew.posix(os.path.join(folder, "state.json")), remote_state_file=remote_dir + "/state.json",
                remote_dir=remote_dir, started=crew.now(), request=job["request"], done_when=a.done)


def create_worktree(repo, meta):
    host, repo_path, worktree = meta["host"], meta["repo_path"], meta["worktree"]
    if not path_exists(host, repo_path + "/.git"):
        raise Fail("repo", "%s:%s is missing: run scripts/vps-setup.sh, or git clone %s %s on %s" % (host, repo_path, repo["remote"], repo_path, host))
    if path_exists(host, worktree):
        raise Fail("worktree", "%s:%s already exists" % (host, worktree))
    ssh(host, "git -C %s fetch --quiet origin" % shlex.quote(repo_path), "fetch")
    ssh(host, "git -C %s worktree add -b %s %s %s" % (shlex.quote(repo_path), shlex.quote(meta["branch"]), shlex.quote(worktree), shlex.quote(meta["base"])), "worktree")
    meta["base_sha"] = ssh(host, "git -C %s rev-parse HEAD" % shlex.quote(worktree), "worktree").strip()


def upload(meta, home, context_block):
    host, folder = meta["host"], os.path.join(crew.STATE, meta["name"])
    os.makedirs(folder, exist_ok=True)
    brief = crew.BRIEF.format(home=home + "/home-repo", context_block=context_block, **dict(meta, report=meta["remote_report"]))
    brief = ASK_COMMAND.sub('python3 "%s/ask.py"' % meta["remote_dir"], brief)
    crew.write_text(os.path.join(folder, "brief.md"), brief)
    put(host, meta["brief"], brief)
    put(host, meta["remote_dir"] + "/ask.py", ASK_SCRIPT)
    extension = absolute(STATE_DIR, home) + "/crew-state.ts"
    put(host, extension, crew.file_text(crew.EXTENSION))
    return extension


def wait_idle(meta, pane, timeout):
    host, deadline = meta["host"], time.time() + timeout
    while True:
        text = ssh(host, "cat %s 2>/dev/null || true" % shlex.quote(meta["remote_state_file"]))
        if text.strip():
            mirror(meta["state_file"], text)
        if crew.file_state(meta["state_file"]).get("state") == "idle":
            return
        if time.time() > deadline:
            screen = crew.herdr("agent", "pane", "read", pane, "--source", "recent-unwrapped", "--lines", "15")
            tail = " | ".join(line.strip() for line in str(screen).splitlines()[-6:] if line.strip())
            raise Fail("agent", "Pi on %s did not become ready in %ds; the pane shows: %s" % (host, timeout, tail))
        time.sleep(2)


def start_pi(a, meta, home, extension):
    host, crew_home = meta["host"], absolute(CREW_HOME, home)
    pane = crew.find(workspace_tab(host, home, meta, crew_home + "/bin/herdr"), ("pane_id",))
    if not pane:
        raise Fail("pane", "Herdr on %s did not return a pane id" % host)
    pane = "@%s:%s" % (host, pane)
    meta["pane"] = pane
    crew.write_meta(meta)
    launch = 'export PATH="%s/bin:$PATH" && "%s/bin/pi" --approve -e "%s" --model %s:%s'
    crew.herdr("agent", "pane", "run", pane, launch % (crew_home, crew_home, extension, meta["model"], meta["thinking"]))
    wait_idle(meta, pane, a.start_timeout)
    crew.send("prompt", pane, "Leia o arquivo %s e siga-o." % meta["brief"])


def spawn(a, job):
    host, name = job["host"], job["name"]
    home = ssh(host, 'printf %s "$HOME"', "host").strip()
    meta = describe(a, job, home)
    if a.dry_run:
        return dict(ok=True, dry_run=True, **meta)

    create_worktree(job["repo"], meta)
    extension = upload(meta, home, job["context_block"])
    crew.write_meta(meta)
    try:
        start_pi(a, meta, home, extension)
    except Fail as e:
        meta["error"] = dict(step=e.step, error=e.error)
        crew.write_meta(meta)
        crew.emit("spawn_failed", name, step=e.step, error=e.error)
        raise Fail(e.step, "%s (worktree %s:%s and state kept; fix and `close %s` before retrying)" % (e.error, host, meta["worktree"], name)) from e
    crew.emit("spawned", name, repo=a.repo, type=meta["type"], model="%s:%s" % (job["model"], job["level"]), host=host)
    if not crew.watcher_alive() and os.environ.get("HERDR_PANE_ID"):
        crew.start_watcher(crew.my_pane("watch"))
    return dict(ok=True, watching=bool(os.environ.get("HERDR_PANE_ID")), **meta)


def workspace_tab(host, home, meta, herdr_bin):
    listed = herdr(host, "pane", "workspace", "list")
    workspace = None
    for ws in (listed.get("result", {}).get("workspaces", []) if isinstance(listed, dict) else []):
        if ws.get("label") == crew.CREW_WORKSPACE:
            workspace = ws["workspace_id"]
    if not workspace:
        made = herdr(host, "pane", "workspace", "create", "--label", crew.CREW_WORKSPACE, "--cwd", home, "--no-focus")
        workspace = crew.find(made, ("workspace_id",))
    if not workspace:
        raise Fail("pane", "Herdr on %s did not return the id of the `%s` workspace" % (host, crew.CREW_WORKSPACE))
    return herdr(host, "pane", "tab", "create", "--workspace", workspace, "--cwd", meta["worktree"], "--label", meta["name"], "--no-focus",
                 "--env", "CREW_STATE_FILE=" + meta["remote_state_file"], "--env", "CREW_AGENT_NAME=" + meta["name"],
                 "--env", "CREW_HERDR_BIN=" + herdr_bin)
