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

export default function (pi: any) {
  const pane = process.env.HERDR_ENV === "1" ? process.env.HERDR_PANE_ID : undefined;
  let file: string | undefined;
  let name: string | undefined;
  let named = false;
  let turns = 0;

  const herdr = (args: string[], done?: () => void) => {
    withoutBreakingTheSession(() => {
      execFile("herdr", args, { windowsHide: true }, () => done?.());
    });
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
    write("idle");
  });
  pi.on("agent_start", async () => write("working"));
  pi.on("agent_settled", async () => {
    turns += 1;
    write("idle");
  });
  pi.on("session_shutdown", async () => write("gone"));
}
