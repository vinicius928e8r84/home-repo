import type { Component, TUI } from "@earendil-works/pi-tui";
import {
  CALM_WORKING_SHIP_TICK_MS,
  CALM_WORKING_SHIP_TICKS_PER_MOVE,
  createCalmWorkingShipSprite,
  type CalmWorkingShipColor,
  type CalmWorkingShipRun,
  type CalmWorkingShipSprite,
} from "./crew-calm-robot-sprite.ts";

export { CALM_WORKING_SHIP_TICK_MS, CALM_WORKING_SHIP_TICKS_PER_MOVE };

const ANSI_FOREGROUND: Record<Exclude<CalmWorkingShipColor, "plain">, string> = {
  bits: "\u001b[32m",
  robot: "\u001b[36m",
  coin: "\u001b[33m",
  alert: "\u001b[31m",
  sweat: "\u001b[34m",
  dim: "\u001b[90m",
};
const RESET = "\u001b[39m";

export const CALM_WORKING_SHIP_WIDGET_KEY = "calm-working-ship";

export type CalmWorkingShipAnimation = Omit<CalmWorkingShipSprite, "frame"> & {
  render(width: number): string[];
};

function paintRun(run: CalmWorkingShipRun): string {
  if (run.color === "plain") return run.text;
  return `${ANSI_FOREGROUND[run.color]}${run.text}${RESET}`;
}

export function createCalmWorkingShipAnimation(): CalmWorkingShipAnimation {
  const sprite = createCalmWorkingShipSprite();
  return {
    position: sprite.position,
    direction: sprite.direction,
    waterPhase: sprite.waterPhase,
    restoreLastRendered: sprite.restoreLastRendered,
    reset: sprite.reset,
    clampToWidth: sprite.clampToWidth,
    tick: sprite.tick,
    render(width: number): string[] {
      return sprite.frame(width).map((row) => row.map(paintRun).join(""));
    },
  };
}

export function createCalmWorkingShipWidget(
  tui: TUI,
  animation: CalmWorkingShipAnimation = createCalmWorkingShipAnimation(),
): Component & { dispose(): void } {
  let disposed = false;
  const timer = setInterval(() => {
    if (disposed) return;
    animation.tick();
    tui.requestRender();
  }, CALM_WORKING_SHIP_TICK_MS);
  timer.unref?.();

  return {
    render: (width) => (disposed ? [] : animation.render(width)),
    invalidate: () => {},
    dispose: () => {
      if (disposed) return;
      disposed = true;
      clearInterval(timer);
      animation.restoreLastRendered();
    },
  };
}
