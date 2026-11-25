import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPTS)
EXTENSION = os.path.join(ROOT, ".pi", "extensions", "crew-state.ts")
BASH = shutil.which("bash")
PONTE = os.path.join(SCRIPTS, "vps-ponte.sh").replace("\\", "/")

HARNESS = '''import cp from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import { pathToFileURL } from "node:url";

Object.defineProperty(process, "platform", { value: "linux" });
const calls = [];
cp.execFile = (bin, args, opts, cb) => {
  calls.push(args);
  if (cb) cb(null, "", "");
};
syncBuiltinESMExports();
const handlers = {};
const pi = { on: (name, handler) => { handlers[name] = handler; } };
process.argv = [process.execPath, "pi", ...JSON.parse(process.env.PI_ARGS)];
const module = await import(pathToFileURL(process.env.EXTENSION).href);
module.default(pi);
const ctx = { cwd: process.env.PI_CWD, sessionManager: { getSessionFile: () => process.env.PI_SESSION } };
await handlers.session_start({}, ctx);
await handlers.agent_start({}, ctx);
await handlers.agent_settled({}, ctx);
console.log(JSON.stringify(calls));
'''


class Retomada(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_extension(self, args, session_exists=True, session_name="sessao.jsonl"):
        session = os.path.join(self.tmp, session_name)
        if session_exists:
            with open(session, "w", encoding="utf-8") as f:
                f.write("{}")
        harness = os.path.join(self.tmp, "harness.mjs")
        with open(harness, "w", encoding="utf-8") as f:
            f.write(HARNESS)
        env = dict(
            os.environ,
            HERDR_ENV="1",
            HERDR_PANE_ID="w1:p2",
            CREW_STATE_FILE=os.path.join(self.tmp, "state.json"),
            CREW_AGENT_NAME="ana",
            CREW_HERDR_BIN="herdr-de-mentira",
            PI_CODING_AGENT_DIR="/crew/pi-agent",
            PATH="/crew/bin:/usr/bin",
            EXTENSION=EXTENSION,
            PI_ARGS=json.dumps(args),
            PI_CWD=self.tmp,
            PI_SESSION=session,
        )
        done = subprocess.run(["node", harness], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1]), session

    def resumes(self, calls):
        return [call for call in calls if "--source" in call and call[call.index("--source") + 1] == "herdr:pi"]

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_resume_command_carries_env_extension_model_and_session(self):
        calls, session = self.run_extension(["--approve", "-e", "/crew/crew-state.ts", "--model", "claude/haiku:low", "--session", "/velha.jsonl"])
        resumes = self.resumes(calls)
        self.assertEqual(len(resumes), 3)
        report = resumes[-1]
        self.assertEqual(report[:3], ["pane", "report-agent", "w1:p2"])
        self.assertEqual(report[report.index("--agent-session-path") + 1], session)
        command = report[report.index("--") + 1:]
        self.assertEqual(command[0], "env")
        self.assertIn("CREW_STATE_FILE=" + os.path.join(self.tmp, "state.json"), command)
        self.assertIn("CREW_AGENT_NAME=ana", command)
        self.assertIn("PI_CODING_AGENT_DIR=/crew/pi-agent", command)
        self.assertIn("PATH=/crew/bin:/usr/bin", command)
        words = command[command.index("pi"):]
        self.assertEqual(words, ["pi", "--approve", "-e", "/crew/crew-state.ts", "--model", "claude/haiku:low", "--session", session])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_resume_report_follows_the_crew_report_and_its_seq_only_grows(self):
        calls, _ = self.run_extension(["--approve"])
        order = [call[call.index("--source") + 1] for call in calls if "--source" in call]
        self.assertEqual(order[:2], ["crew", "herdr:pi"])
        seqs = [int(call[call.index("--seq") + 1]) for call in self.resumes(calls)]
        self.assertEqual(seqs, sorted(set(seqs)))
        self.assertGreater(seqs[0], 10 ** 15)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_no_resume_before_the_session_file_exists(self):
        calls, _ = self.run_extension(["--approve"], session_exists=False)
        self.assertEqual(self.resumes(calls), [])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_no_resume_when_an_argument_would_break_herdr(self):
        calls, _ = self.run_extension(["--approve", "--model", "it's"])
        self.assertEqual(self.resumes(calls), [])


@unittest.skipUnless(BASH, "bash is not installed")
class Ponte(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.crew = os.path.join(self.home, ".local", "share", "crew")
        self.bin = os.path.join(self.tmp, "bin")
        self.log = os.path.join(self.tmp, "log")
        os.makedirs(os.path.join(self.crew, "bin"))
        os.makedirs(self.bin)
        with open(os.path.join(self.home, ".bashrc"), "w", encoding="utf-8") as f:
            f.write("export A=1\ncase $- in\n  *i*) ;;\n  *) return;;\nesac\n")
        self.script(os.path.join(self.crew, "bin", "herdr"), 'echo "real $*" >> "%s"\n[ "$3" = status ] && [ -e "%s/up" ] && echo "status: running"\nexit 0' % (self.log, self.tmp))
        self.script(os.path.join(self.bin, "systemctl"), 'echo "systemctl $*" >> "%s"\n[ -e "%s/unit-works" ] && touch "%s/up"\nexit 0' % (self.log, self.tmp, self.tmp))

    def script(self, path, body):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/usr/bin/env bash\n" + body + "\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def touch(self, name):
        with open(os.path.join(self.tmp, name), "w", encoding="utf-8"):
            pass

    def posix(self, path):
        return path.replace("\\", "/")

    def env(self):
        return dict(os.environ, HOME=self.posix(self.home), CREW_HOME=self.posix(self.crew), PATH=self.posix(self.bin) + os.pathsep + os.environ["PATH"])

    def install(self):
        done = subprocess.run([BASH, PONTE], env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return self.posix(os.path.join(self.crew, "ponte", "herdr"))

    def lines(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            return f.read().splitlines()

    def test_install_is_idempotent_and_hooks_the_bashrc_before_the_interactive_guard(self):
        self.install()
        self.install()
        with open(os.path.join(self.home, ".bashrc"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count("LC_CREW_PONTE"), 1)
        self.assertLess(text.index("LC_CREW_PONTE"), text.index("case $- in"))

    def test_other_commands_go_straight_to_the_crew_binary(self):
        ponte = self.install()
        done = subprocess.run([BASH, ponte, "--session", "crew", "pane", "list"], env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.lines(), ["real --session crew pane list"])

    def test_the_bridge_attaches_to_the_running_server_without_starting_anything(self):
        ponte = self.install()
        self.touch("up")
        done = subprocess.run([BASH, ponte, "--session", "crew", "remote-client-bridge", "--idle-timeout-v1"], env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("systemctl", " ".join(self.lines()))
        self.assertEqual(self.lines()[-1], "real --session crew remote-client-bridge --idle-timeout-v1")

    def test_the_bridge_starts_the_unit_when_no_server_answers(self):
        ponte = self.install()
        self.touch("unit-works")
        done = subprocess.run([BASH, ponte, "--session", "crew", "remote-client-bridge", "--idle-timeout-v1"], env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("systemctl --user start crew-herdr.service", self.lines())
        self.assertEqual(self.lines()[-1], "real --session crew remote-client-bridge --idle-timeout-v1")

    def test_the_bridge_never_starts_a_server_of_its_own(self):
        ponte = self.install()
        with open(ponte, encoding="utf-8") as f:
            script = f.read().replace("seq 1 30", "seq 1 1")
        self.script(ponte, script.split("\n", 1)[1])
        done = subprocess.run([BASH, ponte, "--session", "crew-teste", "remote-client-bridge", "--idle-timeout-v1"], env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("not starting another", done.stderr)
        self.assertIn("systemctl --user start crew-herdr-crew-teste.service", self.lines())
        self.assertFalse([line for line in self.lines() if "remote-client-bridge" in line])


if __name__ == "__main__":
    unittest.main()
