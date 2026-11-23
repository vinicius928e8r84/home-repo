import { realpathSync } from "node:fs";
import type { ExtensionAPI, ExtensionUIContext, ToolDefinition, ToolInfo } from "@earendil-works/pi-coding-agent";

// Resolves symlinks before comparing tool-ownership identity below: sourceInfo.path
// values come from independent path-resolution code paths (this module's own
// import.meta.url vs. Pi's extension loader), and macOS alone symlinks /tmp and /var
// to /private/..., so lexical string comparison alone spuriously reads a symlinked
// self-path as a foreign one. Falls back to the raw path for synthetic, non-file
// sourceInfo paths such as "<builtin:read>" or "<inline>", which realpathSync rejects.
const realpathOrSelf = (path: string): string => {
  try {
    return realpathSync(path);
  } catch {
    return path;
  }
};

export type CalmBuiltInClaims = {
  registerAtLoad: (calmActiveAtLoad: boolean) => void;
  activateIfNeeded: (ui: ExtensionUIContext) => void;
  reportLosses: () => void;
};

export function createCalmBuiltInClaims(
  pi: ExtensionAPI,
  wrappedBuiltIns: ToolDefinition<any, any, any>[],
  extensionFile: string,
): CalmBuiltInClaims {
  const extensionRealFile = realpathOrSelf(extensionFile);

  // True once this extension has handled built-in registration for its lifetime:
  // either all seven synchronously at load, or only the uncontested subset during
  // first activation.
  let builtInsRegistered = false;

  // Gate on Calm already being on at load time. This must stay synchronous and
  // unconditional here (see the header of fm-calm.ts): a foreign-claim check is not
  // reachable at this point, while deferral would make restored rows capture the wrong
  // definition. A Calm-off session or reload registers nothing and creates no collision
  // exposure.
  const registerAtLoad = (calmActiveAtLoad: boolean): void => {
    if (calmActiveAtLoad) {
      for (const tool of wrappedBuiltIns) pi.registerTool(tool);
      builtInsRegistered = true;
    }
  };

  // Which of the 7 built-ins are currently owned by a different, non-builtin
  // extension. Only safe to call once every extension has finished loading (see the
  // header of fm-calm.ts); never call this during the factory's own synchronous
  // execution above.
  function contestedBuiltIns(): ToolDefinition<any, any, any>[] {
    let registered: ToolInfo[];
    try {
      registered = pi.getAllTools();
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      console.error(`Firstmate Calm: built-in ownership check unavailable, claiming every built-in unconditionally. ${reason}`);
      return [];
    }
    return wrappedBuiltIns.filter((tool) => {
      const owner = registered.find((info) => info.name === tool.name)?.sourceInfo;
      return owner !== undefined && owner.source !== "builtin" && realpathOrSelf(owner.path) !== extensionRealFile;
    });
  }

  // The first time Calm turns on in a session that started off, claim every
  // uncontested built-in and leave each contested tool and its owning extension
  // untouched. Tell the user which built-in Calm could not take over, since Calm's
  // presentation does not apply to it.
  function activateIfNeeded(ui: ExtensionUIContext): void {
    if (builtInsRegistered) return;
    const contested = contestedBuiltIns();
    const contestedNames = new Set(contested.map((tool) => tool.name));
    for (const tool of wrappedBuiltIns) {
      if (!contestedNames.has(tool.name)) pi.registerTool(tool);
    }
    builtInsRegistered = true;
    if (contested.length === 0) return;
    const names = contested.map((tool) => `"${tool.name}"`).join(", ");
    const plural = contested.length > 1;
    ui.notify(
      `Firstmate Calm: the ${names} built-in tool${plural ? "s are" : " is"} already provided by another extension, so Calm may not fully function for ${plural ? "them" : "it"} this session.`,
      "warning",
    );
    for (const tool of contested) {
      console.error(`Firstmate Calm: skipped claiming built-in "${tool.name}" because another extension already owns it.`);
    }
  }

  // Backstop for the one case activateIfNeeded cannot reach: Calm registered
  // unconditionally at load time because it was already on, without any chance to
  // check for a foreign claim first, so it can still silently lose a name to an
  // earlier-loaded extension. Runs on every session_start reason because a reload
  // rebuilds every extension's registrations from scratch, so last session's clean
  // bill of health does not carry over.
  function reportLosses(): void {
    if (!builtInsRegistered) return;
    let registered: ToolInfo[];
    try {
      registered = pi.getAllTools();
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      console.error(`Firstmate Calm: built-in ownership check unavailable. ${reason}`);
      return;
    }
    for (const tool of wrappedBuiltIns) {
      const owner = registered.find((info) => info.name === tool.name)?.sourceInfo;
      if (owner && owner.source !== "builtin" && realpathOrSelf(owner.path) !== extensionRealFile) {
        console.error(
          `Firstmate Calm: another extension (${owner.path}) also claimed the built-in "${tool.name}" tool and won; Calm's presentation for it is unavailable this session.`,
        );
      }
    }
  }

  return { registerAtLoad, activateIfNeeded, reportLosses };
}
