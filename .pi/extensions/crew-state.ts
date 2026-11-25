import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

function isHomeRepo(cwd: string): boolean {
  return fs.existsSync(path.join(cwd, "scripts", "crew.py"));
}

const SESSION_VALUE_FLAGS = new Set(["--session", "--session-id", "--fork"]);
const RESUME_ENV = ["CREW_STATE_FILE", "CREW_AGENT_NAME", "CREW_HERDR_BIN", "CREW_STATE_DIR", "CREW_REPOS", "PI_CODING_AGENT_DIR", "PI_CODING_AGENT_SESSION_DIR", "PATH"];
const SESSION_SWITCHES = new Set(["--continue", "-c", "--resume", "-r"]);

function resumeCommand(args: string[], env: Record<string, string | undefined>, session: string): string[] | undefined {
  const kept: string[] = [];
  for (let i = 0; i < args.length; i++) {
    if (SESSION_VALUE_FLAGS.has(args[i])) i += 1;
    else if (!SESSION_SWITCHES.has(args[i])) kept.push(args[i]);
  }
  const assignments = Object.entries(env).flatMap(([key, value]) => (value ? [`${key}=${value}`] : []));
  const command = ["env", ...assignments, "pi", ...kept, "--session", session];
  return command.some((word) => /['\u0000-\u001f]/.test(word)) ? undefined : command;
}

function withoutBreakingTheSession(action: () => void): void {
  try {
    action();
  } catch {
    return;
  }
}

export default function (pi: any) {
  const pane = process.env.HERDR_ENV === "1" ? process.env.HERDR_PANE_ID : undefined;
  let file: string | undefined;
  let name: string | undefined;
  let named = false;
  let turns = 0;
  let sessionFile: string | undefined;
  let lastSeq = 0;

  const herdr = (args: string[], done?: () => void) => {
    withoutBreakingTheSession(() => {
      execFile(process.env.CREW_HERDR_BIN || "herdr", args, { windowsHide: true }, () => done?.());
    });
  };

  const registerResume = (state: "idle" | "working") => {
    if (!pane || !file || !name || !sessionFile || process.platform === "win32") return;
    const session = sessionFile;
    if (!fs.existsSync(session)) return;
    const env = Object.fromEntries(RESUME_ENV.map((key) => [key, process.env[key]]));
    const command = resumeCommand(process.argv.slice(2), env, session);
    if (!command) return;
    lastSeq = Math.max(lastSeq + 1, Date.now() * 1000 + 999);
    herdr(["pane", "report-agent", pane, "--source", "herdr:pi", "--agent", "pi", "--state", state, "--seq", String(lastSeq), "--agent-session-path", session, "--", ...command]);
  };

  const write = (state: "idle" | "working" | "gone") => {
    if (file) {
      const target = file;
      withoutBreakingTheSession(() => {
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, JSON.stringify({ state, turns, at: new Date().toISOString(), pane: pane ?? null }));
      });
    }
    if (!pane || !name) return;
    if (state === "gone") {
      herdr(["pane", "release-agent", pane, "--source", "crew", "--agent", "pi"]);
      return;
    }
    herdr(["pane", "report-agent", pane, "--source", "crew", "--agent", "pi", "--state", state], () => {
      registerResume(state);
      if (named) return;
      named = true;
      herdr(["agent", "rename", pane, name!]);
    });
  };

  pi.on("session_start", async (_event: any, ctx: any) => {
    const cwd = ctx?.cwd ?? process.cwd();
    if (process.env.CREW_STATE_FILE) {
      file = process.env.CREW_STATE_FILE;
      name = process.env.CREW_AGENT_NAME;
    } else if (pane && isHomeRepo(cwd)) {
      const dir = process.env.CREW_STATE_DIR || path.join(cwd, "state", "crew");
      file = path.join(dir, "_chief", `${pane.replace(/[^A-Za-z0-9_-]/g, "_")}.json`);
      name = "chief";
    }
    sessionFile = ctx?.sessionManager?.getSessionFile?.();
    write("idle");
  });
  pi.on("agent_start", async () => write("working"));
  pi.on("agent_settled", async () => {
    turns += 1;
    write("idle");
  });
  pi.on("session_shutdown", async () => write("gone"));
}
