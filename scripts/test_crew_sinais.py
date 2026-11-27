import json
import os
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
EXTENSION = os.path.join(os.path.dirname(SCRIPTS), ".pi", "extensions", "crew-state.ts")
NODE = shutil.which("node")

HARNESS = '''import cp from "node:child_process";
import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { pathToFileURL } from "node:url";

let clock = Date.parse("2026-01-01T00:00:00.000Z");
const RealDate = Date;
globalThis.Date = class extends RealDate {
  constructor(...args) { super(...(args.length ? args : [clock])); }
  static now() { return clock; }
};
const timers = [];
globalThis.setInterval = (fn, ms) => {
  const timer = { fn, ms, cleared: false, unref() { return this; } };
  timers.push(timer);
  return timer;
};
globalThis.clearInterval = (timer) => { if (timer) timer.cleared = true; };

const calls = [];
cp.execFile = (bin, args, opts, cb) => {
  calls.push(args);
  if (cb) cb(null, "", "");
};
let diskFull = false;
const realWriteSync = fs.writeSync;
const realWriteFileSync = fs.writeFileSync;
const noSpace = () => Object.assign(new Error("ENOSPC: no space left on device, write"), { code: "ENOSPC" });
fs.writeSync = (fd, ...rest) => {
  if (!diskFull) return realWriteSync(fd, ...rest);
  realWriteSync(fd, '{"state":"idl');
  throw noSpace();
};
fs.writeFileSync = (target, ...rest) => {
  if (!diskFull) return realWriteFileSync(target, ...rest);
  realWriteFileSync(target, '{"state":"idl');
  throw noSpace();
};
syncBuiltinESMExports();

const handlers = {};
const pi = { on: (name, handler) => { handlers[name] = handler; } };
process.argv = [process.execPath, "pi", "--approve"];
const module = await import(pathToFileURL(process.env.EXTENSION).href);
module.default(pi);
const ctx = { cwd: process.env.PI_CWD, mode: process.env.PI_MODE, sessionManager: { getSessionFile: () => undefined, getSessionId: () => process.env.PI_SESSION_ID ?? "sessao" } };
const read = () => (fs.existsSync(process.env.CREW_STATE_FILE) ? fs.readFileSync(process.env.CREW_STATE_FILE, "utf8") : null);

const snapshots = [];
for (const step of JSON.parse(process.env.STEPS)) {
  if (step.tick) {
    for (const timer of timers.filter((t) => !t.cleared)) { clock += timer.ms; timer.fn(); }
  } else if (step.disk !== undefined) {
    diskFull = step.disk;
  } else {
    await handlers[step.on](step.event ?? {}, ctx);
  }
  snapshots.push(read());
}
console.log(JSON.stringify({ snapshots, calls, pid: process.pid, intervals: timers.map((t) => t.ms), cleared: timers.map((t) => t.cleared) }));
'''

START = [dict(on="session_start"), dict(on="agent_start")]


def turn(stop, error=None):
    message = dict(role="assistant", stopReason=stop)
    if error:
        message["errorMessage"] = error
    return dict(on="turn_end", event=dict(type="turn_end", message=message))


SETTLE = dict(on="agent_settled", event=dict(aborted=False))


@unittest.skipUnless(NODE, "node is not installed")
class Sinais(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = os.path.join(self.tmp, "state.json")

    def run_steps(self, steps, mode="tui"):
        harness = os.path.join(self.tmp, "harness.mjs")
        with open(harness, "w", encoding="utf-8") as f:
            f.write(HARNESS)
        env = dict(os.environ, HERDR_ENV="1", HERDR_PANE_ID="w1:p2", CREW_STATE_FILE=self.state, CREW_AGENT_NAME="ana",
                   CREW_HERDR_BIN="herdr-de-mentira", EXTENSION=EXTENSION, PI_CWD=self.tmp, PI_MODE=mode, STEPS=json.dumps(steps))
        done = subprocess.run([NODE, harness], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout.strip().splitlines()[-1])
        out["snapshots"] = [json.loads(s) if s else None for s in out["snapshots"]]
        return out

    def test_an_error_turn_leaves_its_type_and_text_in_the_state(self):
        text = 'ENOSPC: no space left on device, write'
        out = self.run_steps(START + [turn("error", text), SETTLE])
        settled = out["snapshots"][-1]
        self.assertEqual(settled["state"], "idle")
        self.assertEqual(settled["outcome"], dict(type="error", message=text))

    def test_an_aborted_turn_is_recorded_as_aborted(self):
        out = self.run_steps(START + [turn("aborted", "Operation aborted"), SETTLE])
        self.assertEqual(out["snapshots"][-1]["outcome"], dict(type="aborted", message="Operation aborted"))

    def test_a_good_turn_leaves_the_outcome_clean(self):
        out = self.run_steps(START + [turn("error", "overloaded"), SETTLE, dict(on="agent_start"), turn("stop"), SETTLE])
        self.assertEqual(out["snapshots"][3]["outcome"]["type"], "error")
        self.assertIsNone(out["snapshots"][-1]["outcome"])

    def test_the_state_without_any_turn_has_a_clean_outcome(self):
        out = self.run_steps(START)
        self.assertIsNone(out["snapshots"][0]["outcome"])

    def test_the_state_has_the_pid_of_the_pi(self):
        out = self.run_steps(START)
        self.assertEqual(out["snapshots"][0]["pid"], out["pid"])
        self.assertEqual(out["snapshots"][-1]["pid"], out["pid"])

    def test_the_beat_moves_forward_every_30_seconds_without_touching_the_state_time(self):
        out = self.run_steps(START + [dict(tick=True), dict(tick=True)])
        self.assertEqual(out["intervals"], [30000])
        first, second, third = out["snapshots"][1:]
        self.assertEqual(first["state"], third["state"])
        self.assertEqual(first["at"], third["at"])
        self.assertLess(first["beat"], second["beat"])
        self.assertLess(second["beat"], third["beat"])

    def test_the_beat_stops_when_the_pi_leaves(self):
        out = self.run_steps(START + [dict(on="session_shutdown")])
        self.assertEqual(out["cleared"], [True])
        self.assertEqual(out["snapshots"][-1]["state"], "gone")

    def test_a_child_pi_in_print_mode_leaves_the_state_and_herdr_alone(self):
        before = json.dumps(dict(state="working", turns=3, at="2026-01-01T00:00:00.000Z", pid=7, beat="x", outcome=None))
        with open(self.state, "w", encoding="utf-8") as f:
            f.write(before)
        steps = START + [turn("error", "boom"), dict(tick=True), SETTLE, dict(on="session_shutdown")]
        out = self.run_steps(steps, mode="print")
        for snapshot in out["snapshots"]:
            self.assertEqual(snapshot, json.loads(before))
        self.assertEqual(out["calls"], [])
        self.assertEqual(out["intervals"], [])

    def test_a_full_disk_leaves_the_previous_file_whole(self):
        steps = START + [turn("stop"), SETTLE, dict(disk=True), dict(on="agent_start"), turn("error", "boom"), dict(tick=True), SETTLE]
        out = self.run_steps(steps)
        good = out["snapshots"][3]
        self.assertEqual(good["state"], "idle")
        for snapshot in out["snapshots"][4:]:
            self.assertEqual(snapshot, good)
        self.assertEqual([name for name in os.listdir(self.tmp) if "tmp" in name], [])

    def test_the_state_recovers_when_the_disk_has_space_again(self):
        steps = START + [dict(disk=True), turn("error", "boom"), SETTLE, dict(disk=False), dict(tick=True)]
        out = self.run_steps(steps)
        recovered = out["snapshots"][-1]
        self.assertEqual(recovered["state"], "idle")
        self.assertEqual(recovered["outcome"], dict(type="error", message="boom"))

    def test_no_temporary_file_is_left_after_the_writes(self):
        out = self.run_steps(START)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["harness.mjs", "state.json"])
        self.assertEqual(out["snapshots"][-1]["state"], "working")


if __name__ == "__main__":
    unittest.main()
