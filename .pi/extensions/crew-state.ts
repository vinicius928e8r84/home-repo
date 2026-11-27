import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

function isHomeRepo(cwd: string): boolean {
  return fs.existsSync(path.join(cwd, "scripts", "crew.py"));
}

function withoutBreakingTheSession(action: () => void): void {
  try {
    action();
  } catch {
    return;
  }
}

const BEAT_MS = 30000;

type Outcome = { type: string; message: string } | null;

function outcomeOf(message: any): Outcome {
  const type = message?.stopReason;
  if (type !== "error" && type !== "aborted") return null;
  return { type, message: String(message.errorMessage ?? "") };
}

function isOwnConversation(ctx: any): boolean {
  return ctx?.mode === undefined || ctx.mode === "tui";
}

function replaceFile(target: string, text: string): void {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temp = `${target}.${process.pid}.tmp`;
  try {
    const fd = fs.openSync(temp, "w");
    try {
      fs.writeSync(fd, text);
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    fs.renameSync(temp, target);
  } catch (error) {
    fs.rmSync(temp, { force: true });
    throw error;
  }
}

function locate(cwd: string, pane: string | undefined): { file?: string; name?: string } {
  if (process.env.CREW_STATE_FILE) return { file: process.env.CREW_STATE_FILE, name: process.env.CREW_AGENT_NAME };
  if (!pane || !isHomeRepo(cwd)) return {};
  const dir = process.env.CREW_STATE_DIR || path.join(cwd, "state", "crew");
  return { file: path.join(dir, "_chief", `${pane.replace(/[^A-Za-z0-9_-]/g, "_")}.json`), name: "chief" };
}

function createRecord(pane: string | undefined) {
  let file: string | undefined;
  const body = { state: "idle", turns: 0, at: "", pane: pane ?? null, pid: process.pid, outcome: null as Outcome, beat: "" };
  const save = () => {
    if (!file) return;
    try {
      replaceFile(file, JSON.stringify(body));
    } catch {
      return;
    }
  };
  return {
    open(target: string | undefined) {
      file = target;
    },
    state(state: string, turns: number) {
      body.state = state;
      body.turns = turns;
      body.at = body.beat = new Date().toISOString();
      save();
    },
    turnEnd(message: any) {
      body.outcome = outcomeOf(message);
      save();
    },
    beat() {
      body.beat = new Date().toISOString();
      save();
    },
  };
}

function startBeat(tick: () => void): () => void {
  const timer = setInterval(tick, BEAT_MS);
  timer.unref?.();
  return () => clearInterval(timer);
}

export default function (pi: any) {
  const pane = process.env.HERDR_ENV === "1" ? process.env.HERDR_PANE_ID : undefined;
  let file: string | undefined;
  let name: string | undefined;
  let named = false;
  let turns = 0;
  let inert = false;
  let stopBeat: (() => void) | undefined;
  const record = createRecord(pane);

  const herdr = (args: string[], done?: () => void) => {
    withoutBreakingTheSession(() => {
      execFile(process.env.CREW_HERDR_BIN || "herdr", args, { windowsHide: true }, () => done?.());
    });
  };

  const write = (state: "idle" | "working" | "gone") => {
    if (inert) return;
    record.state(state, turns);
    if (!pane || !name) return;
    if (state === "gone") {
      herdr(["pane", "release-agent", pane, "--source", "crew", "--agent", "pi"]);
      return;
    }
    herdr(["pane", "report-agent", pane, "--source", "crew", "--agent", "pi", "--state", state], () => {
      if (named) return;
      named = true;
      herdr(["agent", "rename", pane, name!]);
    });
  };

  pi.on("session_start", async (_event: any, ctx: any) => {
    if (!isOwnConversation(ctx)) {
      inert = true;
      return;
    }
    ({ file, name } = locate(ctx?.cwd ?? process.cwd(), pane));
    record.open(file);
    write("idle");
    if (file) stopBeat = startBeat(() => record.beat());
  });
  pi.on("turn_end", async (event: any) => {
    if (!inert) record.turnEnd(event?.message);
  });
  pi.on("agent_start", async () => write("working"));
  pi.on("agent_settled", async () => {
    turns += 1;
    write("idle");
  });
  pi.on("session_shutdown", async () => {
    stopBeat?.();
    write("gone");
  });
}
