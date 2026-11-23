// Publishes this Pi session's lifecycle state, for scripts/crew.py and for Herdr.
//
// File: a worker gets its path through CREW_STATE_FILE; a session started in the
// Home Repo without it is the chief and writes state/crew/_chief/state.json.
// Herdr: inside a Herdr pane the same state is reported with the Herdr CLI, so the
// session shows in Herdr's agents list under CREW_AGENT_NAME (the chief: "chief").
// Herdr's own Pi integration cannot reach the server on Windows; the CLI can.
import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

function isHomeRepo(cwd: string): boolean {
  return fs.existsSync(path.join(cwd, "scripts", "crew.py"));
}

export default function (pi: any) {
  const pane = process.env.HERDR_ENV === "1" ? process.env.HERDR_PANE_ID : undefined;
  let file: string | undefined;
  let name: string | undefined;
  let named = false;
  let turns = 0;

  const herdr = (args: string[], done?: () => void) => {
    try {
      execFile("herdr", args, { windowsHide: true }, () => done?.());
    } catch {
      // Herdr missing or unreachable must never break the session.
    }
  };

  const write = (state: "idle" | "working" | "gone") => {
    if (file) {
      try {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(file, JSON.stringify({ state, turns, at: new Date().toISOString(), pane: pane ?? null }));
      } catch {
        // A state file that cannot be written must never break the session.
      }
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
    } else if (isHomeRepo(cwd)) {
      file = path.join(cwd, "state", "crew", "_chief", "state.json");
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
