import * as fs from "node:fs";
import * as path from "node:path";

export function chiefFolder(here: string): string | undefined {
  const chief = process.env.HERDR_ENV === "1" && process.env.HERDR_PANE_ID && !process.env.CREW_STATE_FILE;
  return chief && fs.existsSync(path.join(here, "scripts", "crew.py")) ? here : undefined;
}

export function inboxOf(folder: string): string {
  const dir = process.env.CREW_STATE_DIR || path.join(folder, "state", "crew");
  return path.join(dir, "_chief", `${process.env.HERDR_PANE_ID!.replace(/[^A-Za-z0-9_-]/g, "_")}.inbox`);
}
