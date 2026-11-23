// Writes this Pi session's lifecycle state to a file, for scripts/crew.py.
// A worker gets its file through CREW_STATE_FILE; a session started in the
// Home Repo without it is the chief and writes state/crew/_chief/state.json.
import * as fs from "node:fs";
import * as path from "node:path";

function target(cwd: string): string | undefined {
  if (process.env.CREW_STATE_FILE) return process.env.CREW_STATE_FILE;
  if (fs.existsSync(path.join(cwd, "scripts", "crew.py"))) {
    return path.join(cwd, "state", "crew", "_chief", "state.json");
  }
  return undefined;
}

export default function (pi: any) {
  let file: string | undefined;
  let turns = 0;
  const write = (state: string) => {
    if (!file) return;
    try {
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(
        file,
        JSON.stringify({ state, turns, at: new Date().toISOString(), pane: process.env.HERDR_PANE_ID ?? null }),
      );
    } catch {
      // A state file that cannot be written must never break the session.
    }
  };
  pi.on("session_start", async (_event: any, ctx: any) => {
    file = target(ctx?.cwd ?? process.cwd());
    write("idle");
  });
  pi.on("agent_start", async () => write("working"));
  pi.on("agent_settled", async () => {
    turns += 1;
    write("idle");
  });
  pi.on("session_shutdown", async () => write("gone"));
}
