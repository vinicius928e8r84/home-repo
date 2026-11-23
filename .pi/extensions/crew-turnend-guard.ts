import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { encodeFirstmateOperationalInput } from "./lib/fm-operational-input.ts";

const POLL_MS = 2000;

export default function (pi: any) {
  let cwd: string | undefined;
  let followup = false;
  let timer: ReturnType<typeof setInterval> | undefined;

  const deliverInbox = async (inbox: string) => {
    const taken = `${inbox}.taken`;
    try {
      fs.renameSync(inbox, taken);
    } catch {
      return;
    }
    const lines = fs.readFileSync(taken, "utf8").split(/\r?\n/).filter((line) => line.trim());
    fs.rmSync(taken, { force: true });
    if (lines.length === 0) return;
    try {
      await pi.sendUserMessage(encodeFirstmateOperationalInput("watcher", lines.join(" ")), { deliverAs: "followUp" });
    } catch {
      fs.appendFileSync(inbox, lines.join("\n") + "\n");
    }
  };

  pi.on("session_start", async (_event: any, ctx: any) => {
    const here = ctx?.cwd ?? process.cwd();
    const chief = process.env.HERDR_ENV === "1" && process.env.HERDR_PANE_ID && !process.env.CREW_STATE_FILE;
    cwd = chief && fs.existsSync(path.join(here, "scripts", "crew.py")) ? here : undefined;
    if (timer) clearInterval(timer);
    timer = undefined;
    if (!cwd) return;
    const dir = process.env.CREW_STATE_DIR || path.join(cwd, "state", "crew");
    const inbox = path.join(dir, "_chief", `${process.env.HERDR_PANE_ID!.replace(/[^A-Za-z0-9_-]/g, "_")}.inbox`);
    timer = setInterval(() => void deliverInbox(inbox), POLL_MS);
    timer.unref?.();
  });

  pi.on("session_shutdown", async () => {
    if (timer) clearInterval(timer);
    timer = undefined;
  });

  pi.on("agent_settled", async () => {
    if (!cwd) return;
    if (followup) {
      followup = false;
      return;
    }
    const failure = await new Promise<string | undefined>((resolve) => {
      try {
        execFile("python", [path.join(cwd!, "scripts", "crew.py"), "guard"], { cwd, windowsHide: true }, (error, stdout, stderr) =>
          resolve(error ? (stdout || stderr || String(error)).trim() : undefined),
        );
      } catch (error) {
        resolve(String(error));
      }
    });
    if (!failure) return;
    followup = true;
    try {
      await pi.sendUserMessage(
        encodeFirstmateOperationalInput("turn-end-guard", `[crew] O vigia está parado e há worker aberto; não consegui religá-lo, então este turno terminaria às cegas. Resultado de \`python scripts/crew.py guard\`: ${failure}`),
        { deliverAs: "followUp" },
      );
    } catch {
      followup = false;
    }
  });
}
