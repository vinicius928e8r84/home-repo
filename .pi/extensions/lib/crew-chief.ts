import * as fs from "node:fs";
import * as path from "node:path";

export const CHIEF_SESSION = "chief";

export function chiefFolder(here: string, sessionId?: string): string | undefined {
  const chief = process.env.HERDR_ENV === "1" && process.env.HERDR_PANE_ID && !process.env.CREW_STATE_FILE && sessionId === CHIEF_SESSION;
  return chief && fs.existsSync(path.join(here, "scripts", "crew.py")) ? here : undefined;
}

export function chiefDir(folder: string): string {
  return path.join(process.env.CREW_STATE_DIR || path.join(folder, "state", "crew"), "_chief");
}

export function inboxOf(folder: string): string {
  return path.join(chiefDir(folder), "chief.inbox");
}

export function returnOf(folder: string): string {
  return path.join(chiefDir(folder), "chief.volta");
}
