import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
CREW = os.path.join(SCRIPTS, "crew.py")
sys.path.insert(0, SCRIPTS)
import crew_remote

FAKE_SSH = '''import os, shutil, subprocess, sys

args = sys.argv[1:]
rest = []
i = 0
while i < len(args):
    if args[i] == "-o":
        i += 2
        continue
    if args[i] == "-n":
        i += 1
        continue
    rest.append(args[i])
    i += 1
host, words = rest[0], rest[1:]
home = os.environ["FAKE_VPS_HOME"]
if host == "nowhere" or os.path.exists(os.path.join(home, "..", "down")):
    sys.stderr.write("ssh: Could not resolve hostname %s\\n" % host)
    sys.exit(255)
if os.path.exists(os.path.join(home, "..", "banner")):
    sys.stdout.write("Welcome to the host. Last login: yesterday\\n")
command = " ".join(words)
if command.startswith("python3 "):
    command = '"%s" %s' % (sys.executable.replace("\\\\", "/"), command[len("python3 "):])
command = 'export HOME="%s"; %s' % (home, command)
sys.exit(subprocess.run([shutil.which("bash"), "-c", command]).returncode)
'''

FAKE_HERDR = '''import json, os, sys

home = os.environ["HOME"]
args = sys.argv[1:]
assert args[:2] == ["--session", "crew"], args
args = args[2:]
with open(os.path.join(home, "herdr.log"), "a", encoding="utf-8") as f:
    f.write(json.dumps(args) + "\\n")


def reply(result):
    print(json.dumps(dict(id="fake", result=result)))


if args[:2] == ["workspace", "list"]:
    reply(dict(workspaces=[dict(workspace_id="w1", label="crew")]))
elif args[:2] == ["tab", "create"]:
    env = [a.split("=", 1)[1] for a in args if a.startswith("CREW_STATE_FILE=")]
    with open(os.path.join(home, "state-file"), "w", encoding="utf-8") as f:
        f.write(env[0])
    reply(dict(pane=dict(pane_id="w1:p2")))
elif args[:2] == ["pane", "run"]:
    with open(os.path.join(home, "state-file"), encoding="utf-8") as f:
        path = f.read()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(state="idle", turns=0), f)
    reply({})
elif args[:2] == ["pane", "get"]:
    if os.path.exists(os.path.join(home, "closed")):
        sys.stderr.write("pane not found\\n")
        sys.exit(1)
    reply(dict(pane=dict(pane_id=args[2])))
elif args[:2] == ["pane", "read"]:
    print("output of the remote pane")
elif args[:2] == ["pane", "close"]:
    open(os.path.join(home, "closed"), "w").close()
    reply({})
else:
    reply({})
'''


def git(*args, cwd=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout.strip()


def posix(path):
    return os.path.abspath(path).replace("\\", "/")


class RemoteCrewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = posix(tempfile.mkdtemp(prefix="crew-remote-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.vps = self.tmp + "/vps/home"
        self.state = self.tmp + "/state"
        os.makedirs(self.vps + "/.local/share/crew/bin")
        with open(self.tmp + "/fake_ssh.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(FAKE_SSH)
        with open(self.vps + "/fake_herdr.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(FAKE_HERDR)
        with open(self.vps + "/.local/share/crew/bin/herdr", "w", encoding="utf-8", newline="\n") as f:
            f.write('#!/usr/bin/env bash\nexec "%s" "%s/fake_herdr.py" "$@"\n' % (posix(sys.executable), self.vps))
        os.chmod(self.vps + "/.local/share/crew/bin/herdr", 0o755)

        origin = self.tmp + "/origin.git"
        git("init", "-q", "--bare", "-b", "main", origin)
        seed = self.tmp + "/seed"
        git("clone", "-q", origin, seed)
        with open(seed + "/README.md", "w", encoding="utf-8") as f:
            f.write("seed\n")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "seed", cwd=seed)
        git("push", "-q", "origin", "HEAD:main", cwd=seed)
        git("clone", "-q", origin, self.vps + "/home-repo")

        local = self.tmp + "/local-repo"
        git("init", "-q", local)
        repos = dict(
            remote_repo=dict(short="rem", path="~/home-repo", remote=origin, default_branch="main", branch="pi/{task}", host="vps"),
            local_repo=dict(short="loc", path=local, remote=origin, default_branch="main", branch="pi/{task}"),
        )
        repos["home-repo"] = dict(repos["remote_repo"], short="home")
        repos["absent"] = dict(repos["remote_repo"], short="abs", path="~/absent")
        with open(self.tmp + "/repos.json", "w", encoding="utf-8") as f:
            json.dump(repos, f)
        self.env = dict(os.environ, CREW_STATE_DIR=self.state, CREW_REPOS=self.tmp + "/repos.json", FAKE_VPS_HOME=self.vps,
                        CREW_SSH=json.dumps([sys.executable, "-I", self.tmp + "/fake_ssh.py"]))
        self.env.pop("HERDR_PANE_ID", None)
        self.env.pop("HERDR_ENV", None)
        self.env.pop("CREW_HERDR_SESSION", None)

    def crew(self, *args):
        out = subprocess.run([sys.executable, "-I", CREW, *args], env=self.env, capture_output=True, text=True, encoding="utf-8")
        try:
            return json.loads(out.stdout), out
        except ValueError:
            self.fail("no JSON from crew %s: %r %r" % (args, out.stdout, out.stderr))

    def spawn(self, repo="home-repo", task="toy", *extra):
        result, out = self.crew("spawn", repo, task, "--request", "do it", "--done", "it is done", "--start-timeout", "20", *extra)
        self.assertTrue(result["ok"], result)
        return result

    def herdr_log(self):
        with open(self.vps + "/herdr.log", encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_flag_and_repo_host_decide_where_the_worker_runs(self):
        result, _ = self.crew("spawn", "home-repo", "toy", "--request", "x", "--done", "y", "--dry-run")
        self.assertEqual(result["host"], "vps")
        self.assertEqual(result["worktree"], self.vps + "/worktrees/home-repo-toy")
        self.assertEqual(result["brief"], self.vps + "/crew-state/home-toy/brief.md")
        self.assertFalse(os.path.exists(self.vps + "/worktrees"))
        result, _ = self.crew("spawn", "local_repo", "toy", "--request", "x", "--done", "y", "--dry-run")
        self.assertNotIn("host", result)
        result, _ = self.crew("spawn", "local_repo", "toy", "--request", "x", "--done", "y", "--dry-run", "--host", "vps")
        self.assertEqual(result["host"], "vps")
        result, _ = self.crew("spawn", "home-repo", "toy", "--request", "x", "--done", "y", "--dry-run", "--host", "local")
        self.assertNotIn("host", result)

    def test_spawn_builds_the_worker_on_the_host(self):
        result = self.spawn()
        self.assertEqual(result["pane"], "@vps:w1:p2")
        self.assertTrue(os.path.isdir(self.vps + "/worktrees/home-repo-toy"))
        self.assertEqual(git("-C", self.vps + "/worktrees/home-repo-toy", "branch", "--show-current"), "pi/toy")
        with open(self.vps + "/crew-state/home-toy/brief.md", encoding="utf-8") as f:
            brief = f.read()
        self.assertIn(self.vps + "/crew-state/home-toy/report.md", brief)
        self.assertIn(self.vps + "/crew-state/home-toy/ask.py", brief)
        self.assertNotIn(self.state, brief)
        self.assertTrue(os.path.isfile(self.vps + "/crew-state/crew-state.ts"))
        self.assertTrue(os.path.isfile(self.vps + "/crew-state/home-toy/ask.py"))
        log = self.herdr_log()
        tab = next(entry for entry in log if entry[:2] == ["tab", "create"])
        self.assertIn("CREW_STATE_FILE=" + self.vps + "/crew-state/home-toy/state.json", tab)
        self.assertIn("CREW_HERDR_BIN=" + self.vps + "/.local/share/crew/bin/herdr", tab)
        run = next(entry for entry in log if entry[:2] == ["pane", "run"])
        self.assertEqual(run[2], "w1:p2")
        self.assertIn(self.vps + "/.local/share/crew/bin/pi", run[3])
        self.assertIn(self.vps + "/crew-state/crew-state.ts", run[3])
        self.assertIn("claude-bridge/claude-sonnet-5-5:high", run[3])
        self.assertTrue(run[3].startswith('export PATH="%s/.local/share/crew/bin:$PATH" && ' % self.vps), run[3])
        prompt = next(entry for entry in log if entry[:2] == ["pane", "send-text"])
        self.assertIn(self.vps + "/crew-state/home-toy/brief.md", prompt[3])
        self.assertTrue(os.path.isfile(self.state + "/home-toy/state.json"))
        self.assertFalse(os.path.exists(os.path.expanduser("~/worktrees/home-repo-toy")))
        status, _ = self.crew("status")
        self.assertEqual([(w["name"], w["host"], w["state"]) for w in status["workers"]], [("home-toy", "vps", "idle")])

    def test_spawn_refuses_a_repo_that_is_not_on_the_host(self):
        result, _ = self.crew("spawn", "absent", "toy", "--request", "x", "--done", "y")
        self.assertFalse(result["ok"])
        self.assertEqual(result["step"], "repo")
        self.assertIn("vps-setup.sh", result["error"])

    def test_board_pulls_report_and_decisions_from_the_host(self):
        self.spawn()
        remote = self.vps + "/crew-state/home-toy"
        with open(remote + "/report.md", "w", encoding="utf-8") as f:
            f.write("**Resultado**: feito\n")
        ask = subprocess.run([sys.executable, remote + "/ask.py", "posso?", "--recommend", "sim", "--para", "dono"], capture_output=True, text=True,
                             env=dict(os.environ, CREW_STATE_FILE=remote + "/state.json"))
        self.assertEqual(json.loads(ask.stdout)["ok"], True, ask)
        self.crew("board", "--json")
        text = subprocess.run([sys.executable, "-I", CREW, "board"], env=self.env, capture_output=True, text=True, encoding="utf-8").stdout
        self.assertIn("posso?", text)
        self.assertIn("feito", text)
        with open(self.state + "/home-toy/report.md", encoding="utf-8") as f:
            self.assertIn("feito", f.read())
        with open(self.state + "/decisions.jsonl", encoding="utf-8") as f:
            self.assertEqual(len(f.read().strip().splitlines()), 1)
        answer, _ = self.crew("answer", "D1", "pode")
        self.assertTrue(answer["delivered"], answer)
        sent = [entry for entry in self.herdr_log() if entry[:2] == ["pane", "send-text"]][-1]
        self.assertEqual(sent[2], "w1:p2")
        self.assertIn("pode", sent[3])

    def test_an_ask_without_para_from_the_host_is_a_question_to_the_chief(self):
        self.spawn()
        remote = self.vps + "/crew-state/home-toy"
        ask = subprocess.run([sys.executable, remote + "/ask.py", "qual?", "--recommend", "a"], capture_output=True, text=True,
                             env=dict(os.environ, CREW_STATE_FILE=remote + "/state.json"))
        self.assertEqual(json.loads(ask.stdout)["ok"], True, ask)
        board, _ = self.crew("board", "--json")
        self.assertEqual(board["decisions"], [])
        self.assertEqual([(q["id"], q["question"]) for q in board["questions"]], [("P1", "qual?")])

    def test_tell_and_read_go_to_the_host_pane(self):
        self.spawn()
        told, _ = self.crew("tell", "home-toy", "oi")
        self.assertTrue(told["ok"], told)
        sent = [entry for entry in self.herdr_log() if entry[:2] == ["pane", "send-text"]][-1]
        self.assertEqual(sent[2:], ["w1:p2", "[chief] oi"])
        read, _ = self.crew("read", "home-toy")
        self.assertIn("output of the remote pane", read["output"])
        self.assertEqual(read["state"], "idle")

    def test_close_removes_the_remote_worktree_and_pane(self):
        self.spawn()
        refused, _ = self.crew("close", "home-toy")
        self.assertFalse(refused["ok"])
        self.assertIn("not merged", refused["error"])
        closed, _ = self.crew("close", "home-toy", "--force")
        self.assertTrue(closed["ok"], closed)
        self.assertFalse(os.path.exists(self.vps + "/worktrees/home-repo-toy"))
        self.assertTrue(os.path.exists(self.vps + "/closed"))
        self.assertIn("pi/toy", git("-C", self.vps + "/home-repo", "branch"))
        status, _ = self.crew("status")
        self.assertEqual(status["workers"], [])

    def test_an_unreachable_host_fails_clearly_at_spawn(self):
        result, _ = self.crew("spawn", "local_repo", "toy", "--request", "x", "--done", "y", "--host", "nowhere")
        self.assertFalse(result["ok"])
        self.assertEqual(result["step"], "ssh")
        self.assertIn("nowhere", result["error"])
        self.assertFalse(os.path.exists(self.state + "/loc-toy"))

    def test_an_unreachable_host_does_not_make_workers_gone(self):
        self.spawn()
        open(self.tmp + "/vps/down", "w").close()
        status, out = self.crew("status")
        self.assertEqual(status["workers"][0]["state"], "idle")
        self.assertIn("remote sync failed", out.stderr)

    def test_output_that_is_not_json_does_not_break_the_board_or_status(self):
        self.spawn()
        open(self.tmp + "/vps/banner", "w").close()
        for command in (["status"], ["board", "--json"]):
            result, out = self.crew(*command)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("remote sync failed (sync)", out.stderr)
        text = subprocess.run([sys.executable, "-I", CREW, "board"], env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("remote sync failed (sync)", text.stderr)
        status, _ = self.crew("status")
        self.assertEqual(status["workers"][0]["state"], "idle")

    def test_a_cut_or_broken_asks_line_does_not_break_the_board(self):
        self.spawn()
        asks = self.vps + "/crew-state/home-toy/asks.jsonl"
        with open(asks, "w", encoding="utf-8") as f:
            f.write('{"question": "pergunta cort')
        board, out = self.crew("board", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse(os.path.exists(self.state + "/decisions.jsonl"))
        with open(asks, "w", encoding="utf-8") as f:
            f.write('not json at all\n')
        board, out = self.crew("board", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("not a decision", out.stderr)
        with open(asks, "a", encoding="utf-8") as f:
            f.write('{"question": "pergunta inteira", "recommend": "sim"}\n')
        board, out = self.crew("board", "--json")
        self.assertNotIn("not a decision", out.stderr)
        with open(self.state + "/decisions.jsonl", encoding="utf-8") as f:
            self.assertIn("pergunta inteira", f.read())

    def test_a_valid_ask_before_a_broken_one_is_registered_once(self):
        self.spawn()
        asks = self.vps + "/crew-state/home-toy/asks.jsonl"
        with open(asks, "w", encoding="utf-8") as f:
            f.write('{"question": "q1", "recommend": "a"}\nnot json\n{"question": "q2", "recommend": "b"}\n[1]\n')
        for _ in range(3):
            board, out = self.crew("board", "--json")
            self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual([d["question"] for d in board["decisions"]], ["q1", "q2"])
        with open(self.state + "/home-toy/asks.seen", encoding="utf-8") as f:
            self.assertEqual(f.read(), "4")

    def test_git_over_ssh_is_bounded_and_does_not_read_stdin(self):
        argv = crew_remote.git_argv(dict(host="vps", repo_path="/srv/my repo"))
        self.assertIn("-n", argv[:argv.index("vps")])
        self.assertIn("ServerAliveInterval=5", argv)
        self.assertEqual(argv[argv.index("vps") + 1:], ["timeout", "120", "git", "-C", "'/srv/my repo'"])

    def test_a_git_that_hangs_on_the_host_does_not_hold_the_watcher(self):
        self.spawn()
        shim = self.tmp + "/shim"
        os.makedirs(shim)
        with open(shim + "/git", "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/usr/bin/env bash\nexec sleep 60\n")
        os.chmod(shim + "/git", 0o755)
        self.env.update(PATH=shim + os.pathsep + self.env["PATH"], CREW_REMOTE_GIT_TIMEOUT="1")
        started = time.time()
        status, out = self.crew("status")
        self.assertLess(time.time() - started, 40, out.stderr)
        self.assertEqual(status["workers"][0]["state"], "idle")

    def test_only_the_pane_argument_is_routed_to_a_host(self):
        self.assertEqual(crew_remote.pane_on_host(["pane", "send-text", "w1:p2", "@joao:veja"]), (None, ["pane", "send-text", "w1:p2", "@joao:veja"]))
        self.assertEqual(crew_remote.pane_on_host(["pane", "send-text", "@vps:w1:p2", "@joao:veja"]), ("vps", ["pane", "send-text", "w1:p2", "@joao:veja"]))
        self.assertEqual(crew_remote.pane_on_host(["tab", "create", "--label", "@joao:veja"]), (None, ["tab", "create", "--label", "@joao:veja"]))
        self.spawn()
        told, _ = self.crew("tell", "home-toy", "@joao:veja")
        self.assertTrue(told["ok"], told)
        sent = [entry for entry in self.herdr_log() if entry[:2] == ["pane", "send-text"]][-1]
        self.assertEqual(sent[2:], ["w1:p2", "[chief] @joao:veja"])

    def test_crew_bin_comes_first_in_the_path_of_the_host_setup(self):
        with open(os.path.join(SCRIPTS, "vps-setup.sh"), encoding="utf-8") as f:
            lines = [line for line in f if "PATH" in line and ".local/bin" in line]
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertIn("$CREW_HOME/bin:$HOME/.local/bin", line)

    def test_pane_ids_carry_their_host(self):
        self.assertEqual(crew_remote.pane_on_host(["pane", "get", "@vps:w1:p2"]), ("vps", ["pane", "get", "w1:p2"]))
        self.assertEqual(crew_remote.pane_on_host(["pane", "get", "w1:p2"]), (None, ["pane", "get", "w1:p2"]))


if __name__ == "__main__":
    unittest.main()
