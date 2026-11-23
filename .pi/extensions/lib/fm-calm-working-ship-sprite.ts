const LEFT_SAIL = "◿";
const MAST = "│";
const RIGHT_SAIL = "◣";
const HULL_LEFT = "╲";
const HULL_WATER = "▁▁▁";
const HULL_RIGHT = "╱";
const SAIL_OFFSET = 1;

export const CALM_WORKING_SHIP_SAIL = `${LEFT_SAIL}${MAST}${RIGHT_SAIL}`;
export const CALM_WORKING_SHIP_HULL = `${HULL_LEFT}${HULL_WATER}${HULL_RIGHT}`;

function cellCount(text: string): number {
  return Array.from(text).length;
}

const HULL_WIDTH = cellCount(CALM_WORKING_SHIP_HULL);
const SAIL_WIDTH = cellCount(CALM_WORKING_SHIP_SAIL);

export const CALM_WORKING_SHIP_WAVE_BARS = ["▁", "▂", "▃", "▄"] as const;
const WAVE_MAX_LEVEL = CALM_WORKING_SHIP_WAVE_BARS.length - 1;
const WAVE_HALF_LENGTH_MIN = 9;
const WAVE_HALF_LENGTH_SPAN = 5;
const WAVE_TROUGH_RADIUS = 5;

export const CALM_WORKING_SHIP_TICK_MS = 220;
export const CALM_WORKING_SHIP_TICKS_PER_MOVE = 4;

export type CalmWorkingShipColor = "plain" | "water" | "boat";

export type CalmWorkingShipRun = {
  readonly text: string;
  readonly color: CalmWorkingShipColor;
};

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

function trackSpan(width: number): number {
  if (width >= HULL_WIDTH) return width - HULL_WIDTH;
  if (width >= SAIL_WIDTH) return width - SAIL_WIDTH;
  return 0;
}

function halfWaveLength(index: number, negative: boolean): number {
  let value =
    ((negative ? 0xc411 : 0x5ea1) + Math.imul(index + 1, 0x9e3779b1)) >>> 0;
  value ^= value >>> 16;
  value = Math.imul(value, 0x7feb352d) >>> 0;
  value ^= value >>> 15;
  value >>>= 0;
  return WAVE_HALF_LENGTH_MIN + (value % WAVE_HALF_LENGTH_SPAN);
}

function smoothstep(value: number): number {
  const bounded = Math.max(0, Math.min(1, value));
  return bounded * bounded * (3 - 2 * bounded);
}

function waveAmplitude(coordinate: number): number {
  const negative = coordinate < 0;
  let distance = Math.abs(coordinate);
  let rising = true;
  for (let index = 0; ; index += 1) {
    const length = halfWaveLength(index, negative);
    if (distance <= length) {
      const eased = smoothstep(distance / length);
      return (rising ? eased : 1 - eased) * WAVE_MAX_LEVEL;
    }
    distance -= length;
    rising = !rising;
  }
}

function waveLevel(
  column: number,
  hullCenter: number,
  direction: number,
  phase: number,
): number {
  const displacement =
    hullCenter + (direction * phase) / CALM_WORKING_SHIP_TICKS_PER_MOVE;
  const coordinate = column - displacement;
  if (Math.abs(coordinate) <= WAVE_TROUGH_RADIUS) return 0;
  const beyondTrough = coordinate - Math.sign(coordinate) * WAVE_TROUGH_RADIUS;
  return Math.max(
    0,
    Math.min(WAVE_MAX_LEVEL, Math.round(waveAmplitude(beyondTrough))),
  );
}

type Wake = {
  readonly hullCenter: number;
  readonly direction: number;
  readonly phase: number;
};

function waterRuns(from: number, count: number, wake: Wake): CalmWorkingShipRun[] {
  const runs: CalmWorkingShipRun[] = [];
  for (let column = from; column < from + count; column += 1) {
    const level = waveLevel(column, wake.hullCenter, wake.direction, wake.phase);
    runs.push({
      text: CALM_WORKING_SHIP_WAVE_BARS[level] ?? CALM_WORKING_SHIP_WAVE_BARS[0],
      color: "water",
    });
  }
  return runs;
}

const sail = (): CalmWorkingShipRun[] => [{ text: CALM_WORKING_SHIP_SAIL, color: "boat" }];
const hull = (): CalmWorkingShipRun[] => [{ text: CALM_WORKING_SHIP_HULL, color: "boat" }];

function composeFrame(width: number, position: number, wake: Wake): CalmWorkingShipFrame {
  if (width < SAIL_WIDTH) {
    return [waterRuns(0, width, wake)];
  }
  if (width < HULL_WIDTH) {
    return [
      [
        ...waterRuns(0, position, wake),
        ...sail(),
        ...waterRuns(position + SAIL_WIDTH, width - position - SAIL_WIDTH, wake),
      ],
    ];
  }
  return [
    [{ text: " ".repeat(position + SAIL_OFFSET), color: "plain" }, ...sail()],
    [
      ...waterRuns(0, position, wake),
      ...hull(),
      ...waterRuns(position + HULL_WIDTH, width - position - HULL_WIDTH, wake),
    ],
  ];
}

type SpriteState = {
  position: number;
  direction: number;
  span: number;
  phase: number;
  ticks: number;
};

const initialState = (): SpriteState => ({ position: 0, direction: 1, span: 0, phase: 0, ticks: 0 });

function settleDirectionAtEdges(state: SpriteState): void {
  if (state.span <= 0) return;
  if (state.position >= state.span) state.direction = -1;
  else if (state.position <= 0) state.direction = 1;
}

function applyWidth(state: SpriteState, width: number): void {
  if (width <= 0) {
    state.span = 0;
    state.position = 0;
    return;
  }
  state.span = trackSpan(width);
  state.position = Math.min(state.position, state.span);
  settleDirectionAtEdges(state);
}

function advance(state: SpriteState): void {
  state.ticks += 1;
  state.phase = (state.phase + 1) % CALM_WORKING_SHIP_TICKS_PER_MOVE;
  if (state.ticks % CALM_WORKING_SHIP_TICKS_PER_MOVE !== 0) return;
  if (state.span <= 0) {
    state.position = 0;
    return;
  }
  state.position = Math.min(state.span, Math.max(0, state.position + state.direction));
  settleDirectionAtEdges(state);
}

export function createCalmWorkingShipSprite(): CalmWorkingShipSprite {
  const state = initialState();
  let rendered = { ...state };

  return {
    position: () => state.position,
    direction: () => state.direction,
    waterPhase: () => state.phase,

    restoreLastRendered(): void {
      Object.assign(state, rendered);
    },

    reset(): void {
      Object.assign(state, initialState());
      rendered = { ...state };
    },

    clampToWidth(width: number): void {
      applyWidth(state, width);
    },

    tick(): void {
      advance(state);
    },

    frame(width: number): CalmWorkingShipFrame {
      if (width <= 0) return [];

      applyWidth(state, width);

      const hullCenter =
        state.position +
        (width >= HULL_WIDTH
          ? Math.floor(HULL_WIDTH / 2)
          : Math.floor(SAIL_WIDTH / 2));

      const frame = composeFrame(width, state.position, {
        hullCenter,
        direction: state.direction,
        phase: state.phase,
      });

      rendered = { ...state };
      return frame;
    },
  };
}
