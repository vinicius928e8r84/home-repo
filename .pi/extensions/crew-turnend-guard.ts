import { execFile } from "node:child_process";
import * as path from "node:path";
import { chiefFolder } from "./lib/crew-chief.ts";
import { encodeFirstmateOperationalInput } from "./lib/fm-operational-input.ts";

export default function (pi: any) {
  let cwd: string | undefined;
  let followup = false;

  pi.on("session_start", async (_event: any, ctx: any) => {
    cwd = chiefFolder(ctx?.cwd ?? process.cwd(), ctx?.sessionManager?.getSessionId?.());
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
