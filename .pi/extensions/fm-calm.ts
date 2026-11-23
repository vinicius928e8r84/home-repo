// Firstmate's home-persistent Pi transcript presentation toggle.
//
// Verified against Pi 0.81.1, 0.82.0, and 0.84.4, which expose built-in ToolDefinitions, per-slot
// renderers, renderShell: "self", session_start replacement reasons, agent_start and
// agent_settled, ExtensionUIContext.setToolsExpanded(), setWorkingVisible(), setWidget()
// with a disposable component factory, and setHiddenThinkingLabel().
// ./lib/fm-calm-working-ship.ts owns the animated working presentation this file
// installs. The focused tests pin those assumptions but never reject a
// newer Pi solely for its version. The collapsed-thinking, operational-user, and
// queued-operational presentation adapters probe the exact API they patch and degrade
// independently with a diagnostic (see installCalmPresentationAdapter below) if a future
// Pi removes it; Pi still exposes no global renderer for arbitrary built-in or custom rows.
// docs/configuration.md owns the home-local Calm preference contract.
//
// Pi has one first-registration-wins ToolDefinition per tool name, with no merge or
// unregister operation. Keep Calm-off registration empty; keep Calm-on load-time
// registration synchronous because restored rows capture the registry before
// session_start; and collision-check only the later first-activation path, when
// getAllTools() is reliable. docs/calm-mode-feasibility.md owns the Pi-source evidence
// and docs/calm.md owns the user-facing behavior and non-retroactive first-toggle bound.
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ToolDefinition } from "@earendil-works/pi-coding-agent";
import {
  createBashToolDefinition,
  createEditToolDefinition,
  createFindToolDefinition,
  createGrepToolDefinition,
  createLsToolDefinition,
  createReadToolDefinition,
  createWriteToolDefinition,
} from "@earendil-works/pi-coding-agent";
import { getKeybindings } from "@earendil-works/pi-tui";
import { installCalmAssistantLayout } from "./lib/fm-calm-assistant-layout.ts";
import { createCalmBuiltInClaims } from "./lib/fm-calm-builtin-claims.ts";
import { installCalmOperationalUserLayout } from "./lib/fm-calm-operational-user-layout.ts";
import {
  installCalmPendingOperationalLayout,
  refreshCalmPendingOperationalRows,
} from "./lib/fm-calm-pending-operational-layout.ts";
import { createCalmPreferenceStore } from "./lib/fm-calm-preference.ts";
import { createCalmToolWrapper } from "./lib/fm-calm-tool-wrapper.ts";
import {
  calmPresentationIsActive,
  FIRSTMATE_CALM_PRESENTATION_EVENT,
  registerFirstmateSyntheticPresentation,
  setCalmPresentation,
  setCalmStockExportRendering,
} from "./lib/fm-calm-visibility.ts";
import { createCalmWorkingPresentation } from "./lib/fm-calm-working-presentation.ts";

const extensionFile = fileURLToPath(import.meta.url);
const extensionDir = dirname(extensionFile);
const root = resolve(extensionDir, "../..");

// Each presentation adapter probes the exact Pi API it patches. If a future Pi removes
// that API, only the affected adapter degrades; the rest of Calm keeps working.
function installCalmPresentationAdapter(name: string, install: () => void): void {
  try {
    install();
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    console.error(`Firstmate Calm: ${name} presentation adapter unavailable, skipping. ${reason}`);
  }
}

export default function (pi: ExtensionAPI) {
  installCalmPresentationAdapter("collapsed-thinking", installCalmAssistantLayout);
  installCalmPresentationAdapter("operational-user-row", installCalmOperationalUserLayout);
  installCalmPresentationAdapter("queued-operational-row", installCalmPendingOperationalLayout);

  let exportRendering = false;
  let removeTerminalInputHandler: (() => void) | undefined;
  const workingPresentation = createCalmWorkingPresentation();

  const preference = createCalmPreferenceStore(root);

  const publishPresentationState = (): void => {
    pi.events.emit(FIRSTMATE_CALM_PRESENTATION_EVENT, {
      active: calmPresentationIsActive(),
      stockExportRendering: exportRendering,
    });
  };

  registerFirstmateSyntheticPresentation(pi);

  // Every on-screen tool row Calm currently presents, keyed by the row-local state Pi
  // hands its render slots, so Calm can repaint exactly those rows without touching
  // Pi's transcript. Pi can re-render a row at any time - the built-in edit row
  // invalidates itself once its diff is ready - so a row can be redrawn during the
  // window where /export forces stock rendering and keep that stock content
  // afterwards. Rows Pi's exporter renders are excluded: those use throwaway state
  // and never appear on screen. Cleared per session lifetime, which rebuilds the rows.
  const calmToolRowRepaints = new Map<object, () => void>();
  const rememberCalmToolRow = (state: object, invalidate: unknown): void => {
    if (exportRendering || typeof invalidate !== "function") return;
    calmToolRowRepaints.set(state, invalidate as () => void);
  };
  const repaintCalmToolRows = (): void => {
    for (const invalidate of calmToolRowRepaints.values()) invalidate();
  };

  const wrapBuiltIn = createCalmToolWrapper({
    isExportRendering: () => exportRendering,
    rememberToolRow: rememberCalmToolRow,
  });

  // Each wrapBuiltIn() call below has its own concrete TParams/TDetails/TState; the
  // array holding all seven has no single sound instantiation, so it is typed the same
  // way Pi's own ToolDefinition consumers erase this (any, any, any).
  const wrappedBuiltIns: ToolDefinition<any, any, any>[] = [
    wrapBuiltIn(createReadToolDefinition),
    wrapBuiltIn(createBashToolDefinition),
    wrapBuiltIn(createEditToolDefinition),
    wrapBuiltIn(createWriteToolDefinition),
    wrapBuiltIn(createGrepToolDefinition),
    wrapBuiltIn(createFindToolDefinition),
    wrapBuiltIn(createLsToolDefinition),
  ];

  const builtInClaims = createCalmBuiltInClaims(pi, wrappedBuiltIns, extensionFile);
  builtInClaims.registerAtLoad(preference.load());

  pi.on("session_start", (_event, ctx) => {
    builtInClaims.reportLosses();
    calmToolRowRepaints.clear();
    exportRendering = false;
    setCalmPresentation(preference.load());
    setCalmStockExportRendering(false);
    publishPresentationState();
    workingPresentation.resetForSession();
    workingPresentation.apply(ctx.ui, true);
    ctx.ui.setHiddenThinkingLabel(calmPresentationIsActive() ? "" : undefined);
    ctx.ui.setStatus("firstmate-calm", undefined);
    removeTerminalInputHandler?.();
    removeTerminalInputHandler = ctx.ui.onTerminalInput((data) => {
      if (!getKeybindings().matches(data, "tui.input.submit")) return undefined;

      const input = ctx.ui.getEditorText().trim();
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
      setTimeout(() => {
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
        ctx.ui.setStatus("firstmate-calm", undefined);
      }, 0);
      return undefined;
    });
  });

  pi.on("agent_start", (_event, ctx) => {
    workingPresentation.setAgentRunActive(true);
    workingPresentation.apply(ctx.ui);
  });

  // agent_settled is emitted from a finally block, so it also covers abort and failure.
  pi.on("agent_settled", (_event, ctx) => {
    workingPresentation.setAgentRunActive(false);
    workingPresentation.apply(ctx.ui);
  });

  pi.on("session_shutdown", (_event, ctx) => {
    workingPresentation.setAgentRunActive(false);
    workingPresentation.apply(ctx.ui);
  });

  pi.registerCommand("calm", {
    description: "Toggle Firstmate's supported conversation-only transcript presentation.",
    handler: async (_args, ctx) => {
      const active = !calmPresentationIsActive();
      preference.persist(active);
      setCalmPresentation(active);
      if (active) builtInClaims.activateIfNeeded(ctx.ui);
      publishPresentationState();
      workingPresentation.apply(ctx.ui, true);
      // Pi re-runs every assistant row's layout from this call even when the label is
      // unchanged, which is what makes a toggle apply to rows already on screen.
      ctx.ui.setHiddenThinkingLabel(active ? "" : undefined);
      ctx.ui.setStatus("firstmate-calm", undefined);
      refreshCalmPendingOperationalRows();

      const expanded = ctx.ui.getToolsExpanded();
      ctx.ui.setToolsExpanded(!expanded);
      ctx.ui.setToolsExpanded(expanded);
    },
  });
}
