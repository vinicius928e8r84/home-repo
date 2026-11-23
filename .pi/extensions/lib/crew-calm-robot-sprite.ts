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

      const passed = (column: number): boolean =>
        direction === 1 ? column < position : column > position + ROBOT_WIDTH - 1;
      const coins: number[] = [];
      for (let column = COIN_FIRST; column < width - 2; column += COIN_EVERY) coins.push(column);
      for (const column of coins) {
        if (passed(column)) put(base, column, "·", "dim");
        else put(base, column, "$", "coin");
      }
      const bug = Math.floor(width / 2) - 4;
      const hasBug = bug > 0 && !coins.includes(bug);
      if (hasBug) put(base, bug, "ж", "alert");

      const front = direction === 1 ? position + ROBOT_WIDTH : position - 1;
      const coinAhead = coins.some((column) => !passed(column) && Math.abs(column - front) <= 2);
      const onBug = hasBug && bug >= position && bug <= position + ROBOT_WIDTH - 1;
      const pastBug = direction === 1 ? position - bug : bug - (position + ROBOT_WIDTH - 1);

      let face = "[o_o]";
      let speech = ticks % 2 ? "*┬*" : "·┬·";
      let color: CalmWorkingShipColor = "robot";
      if (ticks % 23 === 0) face = "[-_-]";
      if (ticks % 61 < 6) speech = "brr";
      if (coinAhead) [face, speech, color] = ["[$_$]", "$$$", "coin"];
      if (hasBug && pastBug >= 1 && pastBug <= 2) [face, speech, color] = ["[>_<]", "ops", "robot"];
      if (onBug) [face, speech, color] = ["[x_x]", "404", "alert"];
      put(base, position, face, onBug ? "alert" : "robot");
      put(top, position + 1, speech, color);

      // Sweat flying off the head, behind the robot.
      ["'", "°", "·"].forEach((drop, index) => {
        if ((ticks + index) % 3 === 0) return;
        put(top, direction === 1 ? position - index : position + ROBOT_WIDTH - 1 + index, drop, "sweat");
      });

      rendered = { position, direction, span, ticks };
      return [toRuns(top), toRuns(base)];
    },
  };
}
