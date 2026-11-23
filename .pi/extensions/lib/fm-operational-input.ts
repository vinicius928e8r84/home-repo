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

const MARK = "\u2063";

export function encodeFirstmateOperationalInput(
  kind: FirstmateCurrentOperationalKind,
  content: string,
): string {
  return `${MARK}${kind}${MARK}${content}`;
}

export function classifyFirstmateCurrentOperationalText(
  content: string,
): FirstmateCurrentOperationalKind | undefined {
  if (!content.startsWith(MARK)) return undefined;
  const end = content.indexOf(MARK, 1);
  if (end < 0) return undefined;
  const kind = content.slice(1, end);
  return (FIRSTMATE_CURRENT_OPERATIONAL_KINDS as readonly string[]).includes(kind)
    ? (kind as FirstmateCurrentOperationalKind)
    : undefined;
}

const LEGACY_CALM_OPERATIONAL_PREFIX = "\u2063Supervisor escalate (";

export function isFirstmateOperationalPresentationText(text: string): boolean {
  return (
    classifyFirstmateCurrentOperationalText(text) !== undefined ||
    text.startsWith(LEGACY_CALM_OPERATIONAL_PREFIX)
  );
}
