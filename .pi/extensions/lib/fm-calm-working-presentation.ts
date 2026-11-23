import type { ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import {
  CALM_WORKING_SHIP_WIDGET_KEY,
  createCalmWorkingShipAnimation,
  createCalmWorkingShipWidget,
} from "./fm-calm-working-ship.ts";
import { calmPresentationIsActive } from "./fm-calm-visibility.ts";

export type CalmWorkingPresentation = {
  setAgentRunActive: (active: boolean) => void;
  resetForSession: () => void;
  apply: (ui: ExtensionUIContext, forceStockVisibility?: boolean) => void;
};

export function createCalmWorkingPresentation(): CalmWorkingPresentation {
  // One logical agent run, tracked from agent_start through agent_settled rather than
  // from turns or tool calls, so the boat never flickers between tool calls, automatic
  // continuations, retries, or compaction that stay inside the same run.
  let agentRunActive = false;
  let workingShipShown = false;
  let workingShipWidgetDisposed = false;
  // One animation instance per extension lifetime. Hiding the working widget freezes
  // this state; the next working period resumes it. session_start resets it so a fresh
  // Pi session starts at the normal initial position. Never module-global.
  const workingShipAnimation = createCalmWorkingShipAnimation();

  // Single owner of Calm's working-row presentation choice. The widget is only created
  // or removed on a real transition, so repeated starts cannot duplicate its timer.
  // The slot is shared with standalone Pi Calm; the dispose signal prevents turning
  // Firstmate Calm off from clearing a widget that the other extension installed.
  const apply = (ui: ExtensionUIContext, forceStockVisibility = false): void => {
    const showShip = agentRunActive && calmPresentationIsActive();
    if (showShip !== workingShipShown) {
      workingShipShown = showShip;
      if (showShip) {
        ui.setWidget(CALM_WORKING_SHIP_WIDGET_KEY, (tui) => {
          workingShipWidgetDisposed = false;
          const widget = createCalmWorkingShipWidget(tui, workingShipAnimation);
          const dispose = widget.dispose;
          widget.dispose = () => {
            workingShipWidgetDisposed = true;
            dispose();
          };
          return widget;
        });
        ui.setWorkingVisible(false);
      } else if (!workingShipWidgetDisposed) {
        ui.setWidget(CALM_WORKING_SHIP_WIDGET_KEY, undefined);
        ui.setWorkingVisible(true);
      }
    } else if (forceStockVisibility && !showShip && !workingShipWidgetDisposed) {
      ui.setWorkingVisible(true);
    }
  };

  const setAgentRunActive = (active: boolean): void => {
    agentRunActive = active;
  };

  const resetForSession = (): void => {
    agentRunActive = false;
    workingShipShown = false;
    // A genuine new session lifetime starts the boat at the normal initial position.
    workingShipAnimation.reset();
  };

  return { setAgentRunActive, resetForSession, apply };
}
