import type { ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import { getKeybindings } from "@earendil-works/pi-tui";
import { setCalmStockExportRendering } from "./fm-calm-visibility.ts";

export type CalmExportRendering = {
  isActive: () => boolean;
  rememberToolRow: (state: object, invalidate: unknown) => void;
  resetForSession: () => void;
  onTerminalInput: (ui: ExtensionUIContext) => () => void;
};

export function createCalmExportRendering(publishPresentationState: () => void): CalmExportRendering {
  let exportRendering = false;

  // Every on-screen tool row Calm currently presents, keyed by the row-local state Pi
  // hands its render slots, so Calm can repaint exactly those rows without touching
  // Pi's transcript. Pi can re-render a row at any time - the built-in edit row
  // invalidates itself once its diff is ready - so a row can be redrawn during the
  // window where /export forces stock rendering and keep that stock content
  // afterwards. Rows Pi's exporter renders are excluded: those use throwaway state
  // and never appear on screen. Cleared per session lifetime, which rebuilds the rows.
  const calmToolRowRepaints = new Map<object, () => void>();
  const rememberToolRow = (state: object, invalidate: unknown): void => {
    if (exportRendering || typeof invalidate !== "function") return;
    calmToolRowRepaints.set(state, invalidate as () => void);
  };
  const repaintCalmToolRows = (): void => {
    for (const invalidate of calmToolRowRepaints.values()) invalidate();
  };

  const resetForSession = (): void => {
    calmToolRowRepaints.clear();
    exportRendering = false;
  };

  const finishExport = (ui: ExtensionUIContext): void => {
    exportRendering = false;
    setCalmStockExportRendering(false);
    publishPresentationState();
    // Repaint the rows Calm presents, never the whole transcript. Pi's export
    // prints "Session exported to: <path>" immediately before this runs, and
    // since Pi 0.83.0 setToolsExpanded() emits its own status line; consecutive
    // status lines coalesce, so a tools-expanded round-trip here silently
    // overwrote the confirmation and left the captain no record of where their
    // export landed. Invalidating the rows individually repaints the same
    // content with no status line of its own, and setStatus adds the redraw the
    // rows that consult Calm live in render(), such as operational user rows,
    // need without appending anything to the transcript.
    repaintCalmToolRows();
    ui.setStatus("firstmate-calm", undefined);
  };

  const onTerminalInput = (ui: ExtensionUIContext): (() => void) =>
    ui.onTerminalInput((data) => {
      if (!getKeybindings().matches(data, "tui.input.submit")) return undefined;

      const input = ui.getEditorText().trim();
      if (
        input !== "/share" &&
        input !== "/export" &&
        !input.startsWith("/export ")
      ) {
        return undefined;
      }

      exportRendering = true;
      setCalmStockExportRendering(true);
      publishPresentationState();
      setTimeout(() => finishExport(ui), 0);
      return undefined;
    });

  return { isActive: () => exportRendering, rememberToolRow, resetForSession, onTerminalInput };
}
