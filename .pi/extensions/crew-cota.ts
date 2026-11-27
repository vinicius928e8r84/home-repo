import * as fs from "node:fs";
import * as path from "node:path";

const PREFIX = "anthropic-ratelimit-unified-";
const WINDOWS = ["5h", "7d"];
const HOSTS: Record<string, string> = { win32: "pc", darwin: "mac" };

type Headers = Record<string, string | undefined>;
type Window = { usado: number; reset: string | null; status: string } | null;
type Quota = {
  at: string;
  fonte: string;
  host: string;
  status: string;
  limitante: string | null;
  janelas: Record<string, Window>;
  extra: { status: string | null; reset: string | null; ligado: null; gasto_usd: null; limite_usd: null };
};

function stateDir(cwd: string): string | undefined {
  if (process.env.CREW_STATE_DIR) return process.env.CREW_STATE_DIR;
  return fs.existsSync(path.join(cwd, "scripts", "crew.py")) ? path.join(cwd, "state", "crew") : undefined;
}

function replaceFile(target: string, text: string): void {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temp = `${target}.${process.pid}.tmp`;
  try {
    fs.writeFileSync(temp, text);
    fs.renameSync(temp, target);
  } catch (error) {
    fs.rmSync(temp, { force: true });
    throw error;
  }
}

function isoOf(seconds: string | undefined): string | null {
  if (!seconds || !Number.isFinite(Number(seconds))) return null;
  return new Date(Number(seconds) * 1000).toISOString().replace(/\.\d+Z$/, "Z");
}

function windowOf(headers: Headers, name: string, status: string): Window {
  const used = headers[`${PREFIX}${name}-utilization`];
  if (used === undefined || !Number.isFinite(Number(used))) return null;
  return { usado: Math.round(Number(used) * 100), reset: isoOf(headers[`${PREFIX}${name}-reset`]), status };
}

function quotaOf(headers: Headers): Quota | undefined {
  const status = headers[`${PREFIX}status`];
  if (!status) return undefined;
  const janelas: Record<string, Window> = {};
  for (const name of WINDOWS) janelas[name] = windowOf(headers, name, status);
  return {
    at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
    fonte: "bridge",
    host: HOSTS[process.platform] ?? "vps",
    status,
    limitante: headers[`${PREFIX}representative-claim`] ?? null,
    janelas,
    extra: {
      status: headers[`${PREFIX}overage-status`] ?? null,
      reset: isoOf(headers[`${PREFIX}overage-reset`]),
      ligado: null,
      gasto_usd: null,
      limite_usd: null,
    },
  };
}

function footerOf(quota: Quota): string {
  const shown = (name: string) => (quota.janelas[name] ? `${quota.janelas[name]!.usado}%` : "—");
  const warning = quota.status === "allowed" ? "" : ` · ${quota.status}`;
  return `cota sem ${shown("7d")} · 5h ${shown("5h")}${warning}`;
}

function save(dir: string, quota: Quota): void {
  try {
    replaceFile(path.join(dir, "_cota.json"), JSON.stringify(quota));
  } catch {
    return;
  }
}

function answered(headers: Headers, ctx: any): void {
  const dir = stateDir(ctx.cwd);
  const quota = dir ? quotaOf(headers) : undefined;
  if (!dir || !quota) return;
  save(dir, quota);
  ctx.ui.setStatus("cota", footerOf(quota));
}

export default function (pi: any) {
  pi.on("after_provider_response", async (event: any, ctx: any) => answered(event.headers ?? {}, ctx));
}
