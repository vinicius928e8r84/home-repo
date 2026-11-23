import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const operationalInputScript =
  process.env.FM_OPERATIONAL_INPUT_SCRIPT ||
  resolve(dirname(fileURLToPath(import.meta.url)), "../../../bin/fm-operational-input.sh");

export const FIRSTMATE_CURRENT_OPERATIONAL_KINDS = [
  "session-start",
  "watcher",
  "turn-end-guard",
  "away-supervisor",
  "from-firstmate",
  "launch-brief",
  "branch-outcome",
] as const;

export type FirstmateCurrentOperationalKind =
  (typeof FIRSTMATE_CURRENT_OPERATIONAL_KINDS)[number];

type OperationalInputCommand = "encode" | "classify" | "kind";

export function firstmateShellInvocation(
  script: string,
  args: readonly string[],
): { command: string; args: string[] } {
  return process.platform === "win32"
    ? { command: "bash", args: [script, ...args] }
    : { command: script, args: [...args] };
}

function operationalInputArgs(
  command: OperationalInputCommand,
  kind?: FirstmateCurrentOperationalKind,
): string[] {
  return command === "encode" ? [command, kind ?? ""] : [command];
}

function operationalInputAnswer(
  command: OperationalInputCommand,
  status: number | null,
  stdout: string,
): string | undefined {
  if (status !== 0) return undefined;
  return command === "classify" ? stdout.replace(/\n$/, "") : stdout;
}

function runOperationalInputCommand(
  command: OperationalInputCommand,
  content: string,
  kind?: FirstmateCurrentOperationalKind,
): string | undefined {
  const invocation = firstmateShellInvocation(
    operationalInputScript,
    operationalInputArgs(command, kind),
  );
  try {
    const result = spawnSync(invocation.command, invocation.args, {
      encoding: "utf8",
      input: content,
      maxBuffer: 1024 * 1024,
    });
    return operationalInputAnswer(command, result.status, result.stdout ?? "");
  } catch {
    return undefined;
  }
}

function encodeFailure(kind: FirstmateCurrentOperationalKind): Error {
  return new Error(`could not encode Firstmate operational input kind ${kind}`);
}

export function encodeFirstmateOperationalInput(
  kind: FirstmateCurrentOperationalKind,
  content: string,
): string {
  const encoded = runOperationalInputCommand("encode", content, kind);
  if (encoded === undefined) throw encodeFailure(kind);
  return encoded;
}

export type OperationalInputRunner = (
  command: string,
  args: readonly string[],
  options: { input: string },
) => Promise<{ status: number | null; stdout: string }>;

export async function encodeFirstmateOperationalInputWith(
  run: OperationalInputRunner,
  kind: FirstmateCurrentOperationalKind,
  content: string,
): Promise<string> {
  const invocation = firstmateShellInvocation(
    operationalInputScript,
    operationalInputArgs("encode", kind),
  );
  const result = await run(invocation.command, invocation.args, { input: content });
  const encoded = operationalInputAnswer("encode", result.status, result.stdout);
  if (encoded === undefined) throw encodeFailure(kind);
  return encoded;
}

export function classifyFirstmateOperationalText(content: string): string | undefined {
  return runOperationalInputCommand("classify", content);
}

export function classifyFirstmateCurrentOperationalText(
  content: string,
): string | undefined {
  return runOperationalInputCommand("kind", content);
}

const LEGACY_CALM_OPERATIONAL_PREFIX = "\u2063Supervisor escalate (";

export function isFirstmateOperationalPresentationText(text: string): boolean {
  if (!text.includes("\u2063")) return false;
  return (
    classifyFirstmateCurrentOperationalText(text) !== undefined ||
    text.startsWith(LEGACY_CALM_OPERATIONAL_PREFIX)
  );
}
