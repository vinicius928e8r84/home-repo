import * as fs from "node:fs";
import { chiefFolder, inboxOf, returnOf } from "./lib/crew-chief.ts";

const POLL_MS = Number(process.env.CREW_AVISO_MS) || 2000;
const RESUMO = "[resumo]";

const sessionIdOf = (ctx: any): string | undefined => ctx?.sessionManager?.getSessionId?.();

function takeLines(inbox: string): string[] {
  const taken = `${inbox}.taken`;
  try {
    fs.renameSync(inbox, taken);
  } catch {
    return [];
  }
  const lines = fs.readFileSync(taken, "utf8").split(/\r?\n/).filter((line) => line.trim());
  fs.rmSync(taken, { force: true });
  return lines;
}

export default function (pi: any) {
  let timer: ReturnType<typeof setInterval> | undefined;

  const send = async (inbox: string, lines: string[], triggerTurn: boolean) => {
    if (lines.length === 0) return;
    try {
      await pi.sendMessage({ customType: "crew", display: false, content: lines.join("\n") }, { deliverAs: "followUp", triggerTurn });
    } catch {
      fs.appendFileSync(inbox, lines.join("\n") + "\n");
    }
  };

  const deliver = async (inbox: string, comeback: string | undefined) => {
    const lines = [...(comeback ? takeLines(comeback) : []), ...takeLines(inbox)];
    await send(inbox, lines.filter((line) => line.startsWith(RESUMO)), false);
    await send(inbox, lines.filter((line) => !line.startsWith(RESUMO)), true);
  };

  pi.on("session_start", async (_event: any, ctx: any) => {
    if (timer) clearInterval(timer);
    timer = undefined;
    const folder = chiefFolder(ctx?.cwd ?? process.cwd());
    if (!folder) return;
    const inbox = inboxOf(folder, sessionIdOf(ctx));
    const comeback = returnOf(folder, sessionIdOf(ctx));
    timer = setInterval(() => void deliver(inbox, comeback), POLL_MS);
    timer.unref?.();
  });

  pi.on("session_shutdown", async () => {
    if (timer) clearInterval(timer);
    timer = undefined;
  });
}
