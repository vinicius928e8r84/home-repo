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
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { installCalmAssistantLayout } from "./lib/fm-calm-assistant-layout.ts";
import { createCalmBuiltInClaims } from "./lib/fm-calm-builtin-claims.ts";
import { createCalmExportRendering } from "./lib/fm-calm-export-rendering.ts";
import { reportCalmDiagnostic } from "./lib/fm-calm-diagnostic.ts";
import { installCalmOperationalUserLayout } from "./lib/fm-calm-operational-user-layout.ts";
import {
  installCalmPendingOperationalLayout,
  refreshCalmPendingOperationalRows,
} from "./lib/fm-calm-pending-operational-layout.ts";
import { createCalmPreferenceStore } from "./lib/fm-calm-preference.ts";
import { createCalmWrappedBuiltIns } from "./lib/fm-calm-tool-wrapper.ts";
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
    reportCalmDiagnostic(`Firstmate Calm: ${name} presentation adapter unavailable, skipping. ${reason}`);
  }
}

export default function (pi: ExtensionAPI) {
  installCalmPresentationAdapter("collapsed-thinking", installCalmAssistantLayout);
  installCalmPresentationAdapter("operational-user-row", installCalmOperationalUserLayout);
  installCalmPresentationAdapter("queued-operational-row", installCalmPendingOperationalLayout);

  let removeTerminalInputHandler: (() => void) | undefined;
  const workingPresentation = createCalmWorkingPresentation();

  const preference = createCalmPreferenceStore(root);
  const exportRendering = createCalmExportRendering(() => publishPresentationState());

  const publishPresentationState = (): void => {
    pi.events.emit(FIRSTMATE_CALM_PRESENTATION_EVENT, {
      active: calmPresentationIsActive(),
      stockExportRendering: exportRendering.isActive(),
    });
  };

  registerFirstmateSyntheticPresentation(pi);

  const wrappedBuiltIns = createCalmWrappedBuiltIns({
    isExportRendering: exportRendering.isActive,
    rememberToolRow: exportRendering.rememberToolRow,
  });

  const builtInClaims = createCalmBuiltInClaims(pi, wrappedBuiltIns, extensionFile);
  builtInClaims.registerAtLoad(preference.load());

  pi.on("session_start", (_event, ctx) => {
    builtInClaims.reportLosses();
    exportRendering.resetForSession();
    setCalmPresentation(preference.load());
    setCalmStockExportRendering(false);
    publishPresentationState();
    workingPresentation.resetForSession();
    workingPresentation.apply(ctx.ui, true);
    ctx.ui.setHiddenThinkingLabel(calmPresentationIsActive() ? "" : undefined);
    ctx.ui.setStatus("firstmate-calm", undefined);
    removeTerminalInputHandler?.();
    removeTerminalInputHandler = exportRendering.onTerminalInput(ctx.ui);
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
