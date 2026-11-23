// At the end of the chief's turn, with a worker open and the watcher dead, start the watcher again.
// Silent when all is well; the chief hears only when the watcher cannot be restarted, once.
// Only a chief runs it: a Herdr pane in the Home Repo, with no CREW_STATE_FILE (the worker's mark).
// Pattern from firstmate's fm-primary-turnend-guard.ts; the check itself is `crew.py guard`.
import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

export default function (pi: any) {
  let cwd: string | undefined;
  let followup = false;

  pi.on("session_start", async (_event: any, ctx: any) => {
    const here = ctx?.cwd ?? process.cwd();
    const chief = process.env.HERDR_ENV === "1" && process.env.HERDR_PANE_ID && !process.env.CREW_STATE_FILE;
    cwd = chief && fs.existsSync(path.join(here, "scripts", "crew.py")) ? here : undefined;
  });

  pi.on("agent_settled", async () => {
    if (!cwd) return;
    if (followup) {
      followup = false; // the turn this message started ends here: do not guard it again
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
        `[crew] O vigia está parado e há worker aberto; não consegui religá-lo, então este turno terminaria às cegas. Resultado de \`python scripts/crew.py guard\`: ${failure}`,
        { deliverAs: "followUp" },
      );
    } catch {
      followup = false;
    }
  });
}
