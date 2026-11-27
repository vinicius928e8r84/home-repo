import * as fs from "node:fs";
import * as path from "node:path";

export const CHIEF_SESSION = "chief";

export function chiefFolder(here: string): string | undefined {
  const chief = process.env.HERDR_ENV === "1" && process.env.HERDR_PANE_ID && !process.env.CREW_STATE_FILE;
  return chief && fs.existsSync(path.join(here, "scripts", "crew.py")) ? here : undefined;
}

export function chiefDir(folder: string): string {
  return path.join(process.env.CREW_STATE_DIR || path.join(folder, "state", "crew"), "_chief");
}

export function inboxOf(folder: string, sessionId: string | undefined): string {
  const name = sessionId === CHIEF_SESSION ? CHIEF_SESSION : process.env.HERDR_PANE_ID!.replace(/[^A-Za-z0-9_-]/g, "_");
  return path.join(chiefDir(folder), `${name}.inbox`);
}

export function returnOf(folder: string, sessionId: string | undefined): string | undefined {
  return sessionId === CHIEF_SESSION ? path.join(chiefDir(folder), "chief.volta") : undefined;
}
