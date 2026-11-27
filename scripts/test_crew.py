import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHIEF = "w3:p3"
GIT_ENV = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def git(cwd, *args):
    out = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, env=dict(os.environ, **GIT_ENV))
    assert out.returncode == 0, "git %s: %s" % (" ".join(args), out.stderr)
    return out.stdout.strip()


def minutes_ago(n):
    return (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=n)).isoformat(timespec="seconds")


def utc_minutes_ago(n):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=n)).isoformat()


class Clock:

    def __init__(self):
        self.now = 1_000_000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeHerdr:
    def __init__(self, crew):
        self.crew = crew
        self.panes = {CHIEF: dict(alive=True, agent="pi")}
        self.sent = {}
        self.typed = {}
        self.drop_texts = 0
        self.launched = {}
        self.on_close = None
        self.state_files = {}
        self.next_pane = 0
        self.screen = "screen"
        self.handlers = {
            ("pane", "get"): self.pane_get,
            ("pane", "close"): self.pane_close,
            ("workspace", "list"): self.workspace_list,
            ("tab", "create"): self.tab_create,
            ("pane", "run"): self.pane_run,
            ("pane", "send-text"): self.pane_send_text,
            ("pane", "send-keys"): self.pane_send_keys,
            ("pane", "read"): self.pane_read,
        }

    def __call__(self, step, *args):
        handler = self.handlers.get(args[:2])
        if handler is None:
            raise AssertionError("the fake Herdr does not know %r" % (args,))
        return handler(step, *args)

    def pane_get(self, step, *args):
        pane = self.panes.get(args[2])
        if not pane or not pane["alive"]:
            raise self.crew.Fail(step, "pane %s not found" % args[2])
        return {"result": {"pane": dict(pane_id=args[2], agent=pane["agent"])}}

    def pane_close(self, step, *args):
        self.panes[args[2]]["alive"] = False
        if self.on_close:
            self.on_close()
        return {}

    def workspace_list(self, step, *args):
        return {"result": {"workspaces": [{"label": "crew", "workspace_id": "w9"}]}}

    def tab_create(self, step, *args):
        self.next_pane += 1
        pane = "w9:p%d" % self.next_pane
        self.panes[pane] = dict(alive=True, agent=None)
        env = [args[i + 1] for i, v in enumerate(args) if v == "--env"]
        self.state_files[pane] = [e.split("=", 1)[1] for e in env if e.startswith("CREW_STATE_FILE=")][0]
        return {"result": {"pane": {"pane_id": pane}}}

    def pane_run(self, step, *args):
        self.launched[args[2]] = args[3]
        self.panes[args[2]]["agent"] = "pi"
        self.write_state(args[2], "idle", 0)
        return {}

    def pane_send_text(self, step, *args):
        if self.drop_texts > 0:
            self.drop_texts -= 1
        else:
            self.typed[args[2]] = self.typed.get(args[2], "") + args[3]
        return {}

    def pane_send_keys(self, step, *args):
        if args[3] != "enter":
            raise AssertionError("the fake Herdr does not know %r" % (args,))
        text = self.typed.pop(args[2], "")
        if text:
            self.sent.setdefault(args[2], []).append(text)
            if args[2] in self.state_files:
                self.write_state(args[2], "working", 0)
        return {}

    def pane_read(self, step, *args):
        return self.screen

    def write_state(self, pane, state, turns):
        with open(self.state_files[pane], "w", encoding="utf-8") as f:
            json.dump(dict(state=state, turns=turns, at=datetime.datetime.now(datetime.timezone.utc).isoformat()), f)


class CrewCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crew-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = os.path.join(self.tmp, "state")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.repo = self.make_repo()
        repos = os.path.join(self.tmp, "repos.json")
        with open(repos, "w") as f:
            json.dump({"Test": dict(path=self.repo, remote="none", short="t", branch="pi/{task}", default_branch="main")}, f)
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        os.environ.update(CREW_STATE_DIR=self.state, CREW_REPOS=repos, CREW_HERDR_SESSION="test", HERDR_PANE_ID=CHIEF, CREW_LAVISH_HOSTS="",
                          HOME=self.home, USERPROFILE=self.home, **GIT_ENV)
        spec = importlib.util.spec_from_file_location("crew_under_test", os.path.join(HERE, "crew.py"))
        self.crew = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.crew)
        self.clock = Clock()
        self.crew.time = self.clock
        self.herdr = FakeHerdr(self.crew)
        self.crew.herdr = self.herdr
        self.crew.start_watcher = lambda *a, **k: 0
        self.crew.watcher_alive = lambda: True
        self.crew.module("crew_firstmate").ler_recibos = lambda: dict(handled=[], pending=[], replies=[])
        self.crew.module("crew_cota").ler = lambda: dict(providers=[])
        recursos = self.crew.module("crew_recursos")
        recursos.disparar_original = recursos.disparar
        recursos.disparar = lambda: types.SimpleNamespace(poll=lambda: 0)

    def make_repo(self):
        origin = os.path.join(self.tmp, "origin.git")
        repo = os.path.join(self.tmp, "Test")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
        subprocess.run(["git", "clone", "-q", origin, repo], check=True, capture_output=True)
        git(repo, "checkout", "-q", "-b", "main")
        self.commit(repo, "first")
        git(repo, "push", "-q", "origin", "main")
        return repo

    def commit(self, where, name):
        with open(os.path.join(where, name + ".txt"), "w") as f:
            f.write(name)
        git(where, "add", ".")
        git(where, "commit", "-q", "-m", name)
        return git(where, "rev-parse", "HEAD")

    def worker_meta(self, name, pane, fields):
        folder = os.path.join(self.state, name)
        meta = dict(name=name, repo="Test", repo_path=self.repo.replace("\\", "/"), task="job", type="implement", model="x/y", thinking="high",
                    worktree=os.path.join(self.home, "worktrees", "Test-job").replace("\\", "/"), branch="pi/job", base="origin/main",
                    base_sha=git(self.repo, "rev-parse", "HEAD"), brief=folder + "/brief.md", report=folder + "/report.md",
                    state_file=(folder + "/state.json").replace("\\", "/"), started=minutes_ago(30), pane=pane)
        meta.update(fields)
        return meta

    def add_worker(self, name="t-job", pane="w4:p1", agent="pi", **fields):
        turn = dict(state="working", turns=1, at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        for key in turn:
            turn[key] = fields.pop(key, turn[key])
        meta = self.worker_meta(name, pane, fields)
        os.makedirs(os.path.join(self.state, name), exist_ok=True)
        with open(os.path.join(self.state, name, "meta.json"), "w") as f:
            json.dump(meta, f)
        self.herdr.panes[pane] = dict(alive=True, agent=agent)
        self.herdr.state_files[pane] = meta["state_file"]
        with open(meta["state_file"], "w") as f:
            json.dump(turn, f)
        return meta

    def events(self):
        path = os.path.join(self.state, "events.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def add_events(self, events):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, "events.jsonl"), "a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(dict(at=minutes_ago(1), worker="w", **e)) + "\n")

    def watch(self, rounds=1):
        args = types.SimpleNamespace(chief=CHIEF, every=0, stall=20, unstarted=4, rounds=rounds)
        with contextlib.redirect_stdout(io.StringIO()):
            self.crew.cmd_watch(args)

    def told_chief(self):
        inbox = os.path.join(self.state, "_chief", CHIEF.replace(":", "_") + ".inbox")
        if not os.path.exists(inbox):
            return []
        with open(inbox, encoding="utf-8") as f:
            return f.read().splitlines()


class WatcherHistory(CrewCase):

    def old_decisions(self):
        self.add_events([dict(kind="decision_needed", id="D%d" % n, question="q") for n in range(1, 16)])

    def test_missing_cursor_does_not_dump_the_history(self):
        self.old_decisions()
        self.watch()
        self.assertEqual(self.told_chief(), [])

    def test_cursor_cut_short_by_a_killed_watcher_does_not_dump_the_history(self):
        self.old_decisions()
        os.makedirs(self.state, exist_ok=True)
        open(os.path.join(self.state, "notify.cursor"), "w").close()
        self.watch()
        self.assertEqual(self.told_chief(), [])

    def test_announces_only_what_came_after_the_last_notice(self):
        self.old_decisions()
        with open(os.path.join(self.state, "notify.cursor"), "w") as f:
            f.write("15")
        self.add_events([dict(kind="decision_needed", id="D16", question="q")])
        self.watch()
        self.assertEqual(len(self.told_chief()), 1)
        self.assertIn("D16", self.told_chief()[0])
        self.assertNotIn("D15", self.told_chief()[0])
        self.watch()
        self.assertEqual(len(self.told_chief()), 1)


    def test_a_turn_that_ended_alone_does_not_wake_the_chief(self):
        self.add_worker(turns=1)
        self.watch()
        self.assertIn("turn_ended", [e["kind"] for e in self.events()])
        self.assertEqual(self.told_chief(), [])


class SpawnDelivery(CrewCase):

    def spawn(self):
        args = types.SimpleNamespace(repo="Test", task="job", type=None, model=None, request="do it", request_file=None, done="done",
            context=None, host="local", start_timeout=5, prompt_timeout=10, dry_run=False)
        return self.crew.cmd_spawn(args)

    def test_resends_when_the_first_message_is_lost(self):
        self.herdr.drop_texts = 1
        result = self.spawn()
        self.assertTrue(result["ok"])
        pane = result["pane"]
        self.assertEqual(len(self.herdr.sent.get(pane, [])), 1)
        self.assertEqual(json.load(open(result["state_file"]))["state"], "working")

    def test_opens_pi_in_a_conversation_named_after_the_worker(self):
        result = self.spawn()
        self.assertIn("--session-id %s " % result["name"], self.herdr.launched[result["pane"]])

    def test_gives_up_loudly_when_the_message_never_arrives(self):
        self.herdr.drop_texts = 99
        with self.assertRaises(self.crew.Fail) as caught:
            self.spawn()
        self.assertEqual(caught.exception.step, "prompt")
        self.assertIn("spawn_failed", [e["kind"] for e in self.events()])


class CloseIsSilent(CrewCase):

    def test_close_does_not_become_a_gone_notice(self):
        self.add_worker()
        self.herdr.on_close = self.watch
        with contextlib.redirect_stdout(io.StringIO()):
            self.crew.cmd_close(types.SimpleNamespace(name="t-job", force=True))
        kinds = [e["kind"] for e in self.events()]
        self.assertNotIn("gone", kinds)
        self.assertIn("closed", kinds)

    def test_a_pane_that_died_alone_is_still_reported(self):
        self.add_worker()
        self.herdr.panes["w4:p1"]["alive"] = False
        self.watch()
        self.assertIn("gone", [e["kind"] for e in self.events()])


class AgentIsPi(CrewCase):

    def test_flags_a_worker_the_restore_reopened_as_claude(self):
        self.add_worker(agent="claude")
        self.watch()
        flagged = [e for e in self.events() if e["kind"] == "not_pi"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["agent"], "claude")
        self.watch()
        self.assertEqual(len([e for e in self.events() if e["kind"] == "not_pi"]), 1)

    def test_board_lists_it_as_a_problem(self):
        self.add_worker(agent="claude")
        with contextlib.redirect_stdout(io.StringIO()):
            board = self.crew.cmd_board(types.SimpleNamespace(json=True))
        self.assertEqual([m["name"] for m in board["trouble"]], ["t-job"])
        self.assertEqual(board["running"], [])

    def test_a_pi_worker_is_fine(self):
        self.add_worker(agent="pi")
        self.watch()
        self.assertNotIn("not_pi", [e["kind"] for e in self.events()])

    def test_an_agent_not_detected_yet_is_not_an_accusation(self):
        self.add_worker(agent=None)
        self.watch()
        self.assertNotIn("not_pi", [e["kind"] for e in self.events()])


class OpenDecisionIsNotStalled(CrewCase):

    def stalled(self, meta):
        return self.crew.snapshot(meta, False, 20)["stalled"]

    def decision(self, worker, **extra):
        self.crew.log_decision(dict(id="D1", at=minutes_ago(25), worker=worker, repo="Test", question="q", recommend="r", status="open"))
        if extra:
            self.crew.log_decision(dict(id="D1", **extra))

    def test_long_turn_is_stalled(self):
        meta = self.add_worker(at=utc_minutes_ago(30))
        self.assertTrue(self.stalled(meta))

    def test_long_turn_with_an_open_decision_is_not_stalled(self):
        meta = self.add_worker(at=utc_minutes_ago(30))
        self.decision("t-job")
        self.assertFalse(self.stalled(meta))

    def test_a_just_answered_decision_restarts_the_clock(self):
        meta = self.add_worker(at=utc_minutes_ago(30))
        self.decision("t-job", status="answered", answered_at=minutes_ago(1), answer="a")
        self.assertFalse(self.stalled(meta))

    def test_an_old_answered_decision_does_not_hide_a_stall(self):
        meta = self.add_worker(at=utc_minutes_ago(30))
        self.decision("t-job", status="answered", answered_at=minutes_ago(25), answer="a")
        self.assertTrue(self.stalled(meta))

    def test_another_workers_decision_does_not_count(self):
        meta = self.add_worker(at=utc_minutes_ago(30))
        self.decision("someone-else")
        self.assertTrue(self.stalled(meta))


class ProgressIsNotStalled(CrewCase):
    def stalled_when_the_screen_becomes(self, screen):
        meta = self.add_worker(at=utc_minutes_ago(30))
        self.herdr.screen = "before"
        mark = hashlib.sha1(self.crew.progress_mark(meta).encode()).hexdigest()
        with open(os.path.join(self.state, "t-job", "watch.json"), "w") as f:
            json.dump(dict(progress=dict(mark=mark, at=minutes_ago(25))), f)
        self.herdr.screen = screen
        return self.crew.snapshot(meta, False, 20)["stalled"]

    def test_a_screen_that_stays_the_same_is_stalled(self):
        self.assertTrue(self.stalled_when_the_screen_becomes("before"))

    def test_a_screen_that_changed_is_not_stalled(self):
        self.assertFalse(self.stalled_when_the_screen_becomes("a new line"))


class CloseForce(CrewCase):

    def stuck_worker(self):
        meta = self.add_worker()
        os.makedirs(meta["worktree"])
        with open(os.path.join(meta["worktree"], "left-over.txt"), "w") as f:
            f.write("x")
        return meta

    def close(self, force=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.crew.cmd_close(types.SimpleNamespace(name="t-job", force=force))

    def test_force_closes_and_removes_the_stuck_folder(self):
        meta = self.stuck_worker()
        result = self.close()
        self.assertTrue(result["ok"])
        self.assertFalse(os.path.exists(meta["worktree"]))
        self.assertTrue(self.crew.read_meta("t-job").get("closed"))

    def test_force_closes_even_when_the_folder_cannot_be_removed(self):
        meta = self.stuck_worker()
        def held_open(*args, **kwargs):
            raise PermissionError("in use by another process")

        self.crew.shutil = types.SimpleNamespace(which=shutil.which, rmtree=held_open)
        result = self.close()
        self.assertTrue(self.crew.read_meta("t-job").get("closed"))
        self.assertTrue(any(meta["worktree"] in n or "pasta" in n for n in result["notes"]), result["notes"])

    def test_force_leaves_no_ghost_registration_for_a_worktree_git_knows(self):
        meta = self.add_worker()
        git(self.repo, "worktree", "add", "-q", "-b", meta["branch"], meta["worktree"], "origin/main")
        self.assertIn("worktrees/Test-job", git(self.repo, "worktree", "list", "--porcelain").replace("\\", "/"))
        notes = []
        self.crew.drop_folder(meta, notes)
        self.assertFalse(os.path.exists(meta["worktree"]), notes)
        listing = git(self.repo, "worktree", "list", "--porcelain")
        self.assertNotIn("prunable", listing)
        self.assertNotIn("Test-job", listing.replace("\\", "/"))
        git(self.repo, "worktree", "add", "-q", meta["worktree"], meta["branch"])

    def test_force_never_deletes_a_folder_outside_the_worktrees_directory(self):
        outside = os.path.join(self.tmp, "precious")
        os.makedirs(outside)
        self.add_worker(worktree=outside.replace("\\", "/"))
        result = self.close()
        self.assertTrue(os.path.isdir(outside))
        self.assertTrue(self.crew.read_meta("t-job").get("closed"))
        self.assertTrue(result["notes"])


class MergedNeedsOwnCommit(CrewCase):

    def worktree(self, branch):
        path = os.path.join(self.tmp, "wt-" + branch)
        base = git(self.repo, "rev-parse", "origin/main")
        git(self.repo, "worktree", "add", "-q", "-b", branch, path, base)
        return path, base

    def advance_main(self):
        other = os.path.join(self.tmp, "other")
        subprocess.run(["git", "clone", "-q", os.path.join(self.tmp, "origin.git"), other], check=True, capture_output=True)
        self.commit(other, "someone-elses")
        git(other, "push", "-q", "origin", "main")

    def meta_for(self, branch, base):
        return self.add_worker(branch=branch, base_sha=base)

    def test_branch_fast_forwarded_to_main_is_not_merged(self):
        path, base = self.worktree("pi/job")
        self.advance_main()
        git(path, "fetch", "-q", "origin")
        git(path, "merge", "-q", "--ff-only", "origin/main")
        self.assertFalse(self.crew.snapshot(self.meta_for("pi/job", base), True)["merged"])

    def test_branch_with_its_own_commit_that_entered_main_is_merged(self):
        path, base = self.worktree("pi/job")
        self.commit(path, "mine")
        git(path, "push", "-q", "origin", "HEAD:main")
        self.assertTrue(self.crew.snapshot(self.meta_for("pi/job", base), True)["merged"])

    def test_branch_with_its_own_commit_not_yet_in_main_is_not_merged(self):
        path, base = self.worktree("pi/job")
        self.commit(path, "mine")
        self.assertFalse(self.crew.snapshot(self.meta_for("pi/job", base), True)["merged"])

    def test_watcher_does_not_announce_a_merge_for_a_fast_forwarded_branch(self):
        path, base = self.worktree("pi/job")
        self.advance_main()
        git(path, "fetch", "-q", "origin")
        git(path, "merge", "-q", "--ff-only", "origin/main")
        self.meta_for("pi/job", base)
        self.watch()
        self.assertNotIn("merged", [e["kind"] for e in self.events()])


if __name__ == "__main__":
    unittest.main(verbosity=2)
