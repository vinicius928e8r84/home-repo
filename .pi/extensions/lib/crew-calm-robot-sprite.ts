// The Home Repo's Calm working animation: a robot riding a river of bits.
//
// It replaces Firstmate's boat (./fm-calm-working-ship-sprite.ts, kept untouched) and
// exports the same names and the same sprite contract, so ./fm-calm-working-ship.ts
// switches between the two by changing one import path.
//
// The scene: the robot bounces along a stream of 0s and 1s. Sweat flies off its head
// behind it and its antenna sparks. A `$` ahead turns its eyes into `$_$`; the coin is
// spent once passed and comes back on the next sweep. A bug sits mid-track: on it the
// robot shows `[x_x]` under a `404`, and leaves with `[>_<]` and an "ops".
//
// Every glyph is one terminal column, so widths are plain character counts. Ticks, not
// wall-clock time, drive every change, so a frozen sprite resumes exactly where it stopped.

/** Scheduler period. One tick advances the bit stream; every fourth moves the robot. */
export const CALM_WORKING_SHIP_TICK_MS = 220;
export const CALM_WORKING_SHIP_TICKS_PER_MOVE = 4;

/** `plain` is uncolored padding; the harness maps every other class to a color. */
export type CalmWorkingShipColor = "plain" | "bits" | "robot" | "coin" | "alert" | "sweat" | "dim";

export type CalmWorkingShipRun = {
  readonly text: string;
  readonly color: CalmWorkingShipColor;
};

/** One painted frame: one or two rows of runs, each row exactly the requested width. */
export type CalmWorkingShipFrame = readonly (readonly CalmWorkingShipRun[])[];

export type CalmWorkingShipSprite = {
  frame(width: number): CalmWorkingShipFrame;
  tick(): void;
  restoreLastRendered(): void;
  reset(): void;
  clampToWidth(width: number): void;
  position(): number;
  direction(): number;
  waterPhase(): number;
};

const ROBOT_WIDTH = 5;
const COIN_FIRST = 8;
const COIN_EVERY = 11;

type Cell = [glyph: string, color: CalmWorkingShipColor];

function blankRow(width: number): Cell[] {
  return Array.from({ length: width }, (): Cell => [" ", "plain"]);
}

function put(row: Cell[], column: number, text: string, color: CalmWorkingShipColor): void {
  Array.from(text).forEach((glyph, index) => {
    const at = column + index;
    if (at >= 0 && at < row.length) row[at] = [glyph, color];
  });
}

/** Merge neighbouring cells of one color into runs. */
function toRuns(row: Cell[]): CalmWorkingShipRun[] {
  const runs: { text: string; color: CalmWorkingShipColor }[] = [];
  for (const [glyph, color] of row) {
    const last = runs[runs.length - 1];
    if (last && last.color === color) last.text += glyph;
    else runs.push({ text: glyph, color });
  }
  return runs;
}

type Pose = { readonly position: number; readonly direction: number; readonly ticks: number };

type Face = {
  readonly face: string;
  readonly speech: string;
  readonly color: CalmWorkingShipColor;
  readonly onBug: boolean;
};

const hasPassed = (pose: Pose, column: number): boolean =>
  pose.direction === 1 ? column < pose.position : column > pose.position + ROBOT_WIDTH - 1;

function coinColumns(width: number): number[] {
  const coins: number[] = [];
  for (let column = COIN_FIRST; column < width - 2; column += COIN_EVERY) coins.push(column);
  return coins;
}

function paintCoins(base: Cell[], coins: number[], pose: Pose): void {
  for (const column of coins) {
    if (hasPassed(pose, column)) put(base, column, "·", "dim");
    else put(base, column, "$", "coin");
  }
}

function bugColumn(width: number, coins: number[]): number | null {
  const bug = Math.floor(width / 2) - 4;
  return bug > 0 && !coins.includes(bug) ? bug : null;
}

function isOnBug(pose: Pose, bug: number | null): boolean {
  return bug !== null && bug >= pose.position && bug <= pose.position + ROBOT_WIDTH - 1;
}

function isLeavingBug(pose: Pose, bug: number | null): boolean {
  if (bug === null) return false;
  const pastBug = pose.direction === 1 ? pose.position - bug : bug - (pose.position + ROBOT_WIDTH - 1);
  return pastBug >= 1 && pastBug <= 2;
}

function isCoinAhead(pose: Pose, coins: number[]): boolean {
  const front = pose.direction === 1 ? pose.position + ROBOT_WIDTH : pose.position - 1;
  return coins.some((column) => !hasPassed(pose, column) && Math.abs(column - front) <= 2);
}

function chooseFace(pose: Pose, coins: number[], bug: number | null): Face {
  const onBug = isOnBug(pose, bug);
  if (onBug) return { face: "[x_x]", speech: "404", color: "alert", onBug };
  if (isLeavingBug(pose, bug)) return { face: "[>_<]", speech: "ops", color: "robot", onBug };
  if (isCoinAhead(pose, coins)) return { face: "[$_$]", speech: "$$$", color: "coin", onBug };
  return {
    face: pose.ticks % 23 === 0 ? "[-_-]" : "[o_o]",
    speech: pose.ticks % 61 < 6 ? "brr" : pose.ticks % 2 ? "*┬*" : "·┬·",
    color: "robot",
    onBug,
  };
}

function paintSweat(top: Cell[], pose: Pose): void {
  ["'", "°", "·"].forEach((drop, index) => {
    if ((pose.ticks + index) % 3 === 0) return;
    put(top, pose.direction === 1 ? pose.position - index : pose.position + ROBOT_WIDTH - 1 + index, drop, "sweat");
  });
}

function paintScene(base: Cell[], top: Cell[], pose: Pose): void {
  const coins = coinColumns(base.length);
  paintCoins(base, coins, pose);
  const bug = bugColumn(base.length, coins);
  if (bug !== null) put(base, bug, "ж", "alert");
  const look = chooseFace(pose, coins, bug);
  put(base, pose.position, look.face, look.onBug ? "alert" : "robot");
  put(top, pose.position + 1, look.speech, look.color);

  // Sweat flying off the head, behind the robot.
  paintSweat(top, pose);
}

export function createCalmWorkingShipSprite(): CalmWorkingShipSprite {
  let position = 0;
  let direction = 1;
  let span = 0;
  let ticks = 0;
  let rendered = { position, direction, span, ticks };

  const settleDirectionAtEdges = (): void => {
    if (span <= 0) return;
    if (position >= span) direction = -1;
    else if (position <= 0) direction = 1;
  };

  const applyWidth = (width: number): void => {
    span = Math.max(0, width - ROBOT_WIDTH);
    position = Math.min(position, span);
    settleDirectionAtEdges();
  };

  const bits = (width: number): Cell[] => {
    const flow = Math.floor(ticks / 2);
    return Array.from({ length: width }, (_unused, column): Cell => {
      if ((column + flow) % 4 === 0) return [" ", "plain"];
      return ["01"[(column * 31 + flow) & 1] ?? "0", "bits"];
    });
  };

  return {
    position: () => position,
    direction: () => direction,
    waterPhase: () => ticks % CALM_WORKING_SHIP_TICKS_PER_MOVE,
    restoreLastRendered(): void {
      ({ position, direction, span, ticks } = rendered);
    },
    reset(): void {
      position = 0;
      direction = 1;
      span = 0;
      ticks = 0;
      rendered = { position, direction, span, ticks };
    },
    clampToWidth(width: number): void {
      applyWidth(width);
    },
    tick(): void {
      ticks += 1;
      if (ticks % CALM_WORKING_SHIP_TICKS_PER_MOVE !== 0 || span <= 0) return;
      position = Math.min(span, Math.max(0, position + direction));
      settleDirectionAtEdges();
    },
    frame(width: number): CalmWorkingShipFrame {
      if (width <= 0) return [];
      applyWidth(width);
      const base = bits(width);
      if (width < ROBOT_WIDTH) {
        rendered = { position, direction, span, ticks };
        return [toRuns(base)];
      }
      const top = blankRow(width);
      paintScene(base, top, { position, direction, ticks });

      rendered = { position, direction, span, ticks };
      return [toRuns(top), toRuns(base)];
    },
  };
}
