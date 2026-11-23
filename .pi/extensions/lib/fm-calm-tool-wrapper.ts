import type { ToolDefinition, ToolRenderResultOptions } from "@earendil-works/pi-coding-agent";
import {
  createBashToolDefinition,
  createEditToolDefinition,
  createFindToolDefinition,
  createGrepToolDefinition,
  createLsToolDefinition,
  createReadToolDefinition,
  createWriteToolDefinition,
} from "@earendil-works/pi-coding-agent";
import { Box, Container, type Component } from "@earendil-works/pi-tui";
import type { TSchema } from "typebox";
import { calmPresentationHides } from "./fm-calm-visibility.ts";

type DefinitionFactory<TParams extends TSchema, TDetails, TState> = (
  cwd: string,
) => ToolDefinition<TParams, TDetails, TState>;

type RenderContext<TParams extends TSchema, TDetails, TState> = Parameters<
  NonNullable<ToolDefinition<TParams, TDetails, TState>["renderCall"]>
>[2];

type RenderArgs<TParams extends TSchema, TDetails, TState> = Parameters<
  NonNullable<ToolDefinition<TParams, TDetails, TState>["renderCall"]>
>[0];

type RenderTheme<TParams extends TSchema, TDetails, TState> = Parameters<
  NonNullable<ToolDefinition<TParams, TDetails, TState>["renderCall"]>
>[1];

type RenderResult<TParams extends TSchema, TDetails, TState> = Parameters<
  NonNullable<ToolDefinition<TParams, TDetails, TState>["renderResult"]>
>[0];

type StandardShellState = {
  shell?: Box;
  call?: Component;
  result?: Component;
};

export type CalmToolWrapperHooks = {
  isExportRendering: () => boolean;
  rememberToolRow: (state: object, invalidate: unknown) => void;
};

type WrapParts<TParams extends TSchema, TDetails, TState> = {
  hooks: CalmToolWrapperHooks;
  renderCall: NonNullable<ToolDefinition<TParams, TDetails, TState>["renderCall"]>;
  renderResult: NonNullable<ToolDefinition<TParams, TDetails, TState>["renderResult"]>;
  selfShell: boolean;
  shells: WeakMap<object, StandardShellState>;
};

function shellStateFor<TParams extends TSchema, TDetails, TState>(
  shells: WeakMap<object, StandardShellState>,
  context: RenderContext<TParams, TDetails, TState>,
): StandardShellState {
  const rowState = context.state as object;
  let shellState = shells.get(rowState);
  if (!shellState) {
    shellState = {};
    shells.set(rowState, shellState);
  }
  return shellState;
}

function refreshStandardShell<TParams extends TSchema, TDetails, TState>(
  state: StandardShellState,
  theme: RenderTheme<TParams, TDetails, TState>,
  context: RenderContext<TParams, TDetails, TState>,
): Box {
  const background = context.isPartial
    ? (text: string) => theme.bg("toolPendingBg", text)
    : context.isError
      ? (text: string) => theme.bg("toolErrorBg", text)
      : (text: string) => theme.bg("toolSuccessBg", text);
  const shell = state.shell ?? new Box(1, 1, background);
  state.shell = shell;
  shell.setBgFn(background);
  shell.clear();
  if (state.call) shell.addChild(state.call);
  if (state.result) shell.addChild(state.result);
  return shell;
}

function createCalmRenderCall<TParams extends TSchema, TDetails, TState>(
  parts: WrapParts<TParams, TDetails, TState>,
) {
  return (
    args: RenderArgs<TParams, TDetails, TState>,
    theme: RenderTheme<TParams, TDetails, TState>,
    context: RenderContext<TParams, TDetails, TState>,
  ) => {
    parts.hooks.rememberToolRow(context.state as object, context.invalidate);
    if (parts.hooks.isExportRendering()) return parts.renderCall(args, theme, context);
    if (calmPresentationHides("assistant-tool-call")) return new Container();
    if (parts.selfShell) return parts.renderCall(args, theme, context);

    const state = shellStateFor(parts.shells, context);
    state.call = parts.renderCall(args, theme, {
      ...context,
      lastComponent: state.call,
    });
    return refreshStandardShell(state, theme, context);
  };
}

function createCalmRenderResult<TParams extends TSchema, TDetails, TState>(
  parts: WrapParts<TParams, TDetails, TState>,
) {
  return (
    result: RenderResult<TParams, TDetails, TState>,
    options: ToolRenderResultOptions,
    theme: RenderTheme<TParams, TDetails, TState>,
    context: RenderContext<TParams, TDetails, TState>,
  ) => {
    parts.hooks.rememberToolRow(context.state as object, context.invalidate);
    if (parts.hooks.isExportRendering()) return parts.renderResult(result, options, theme, context);
    if (calmPresentationHides("tool-result")) return new Container();
    if (parts.selfShell) return parts.renderResult(result, options, theme, context);

    const state = shellStateFor(parts.shells, context);
    state.result = parts.renderResult(result, options, theme, {
      ...context,
      lastComponent: state.result,
    });
    refreshStandardShell(state, theme, context);
    return new Container();
  };
}

function wrapBuiltIn<TParams extends TSchema, TDetails, TState>(
  factory: DefinitionFactory<TParams, TDetails, TState>,
  hooks: CalmToolWrapperHooks,
): ToolDefinition<TParams, TDetails, TState> {
  const definitions = new Map<string, ToolDefinition<TParams, TDetails, TState>>();
  const definitionFor = (cwd: string): ToolDefinition<TParams, TDetails, TState> => {
    let definition = definitions.get(cwd);
    if (!definition) {
      definition = factory(cwd);
      definitions.set(cwd, definition);
    }
    return definition;
  };

  const original = definitionFor(process.cwd());
  if (!original.renderCall || !original.renderResult) {
    throw new Error(`Firstmate calm mode requires both render slots for Pi built-in tool ${original.name}`);
  }
  const parts: WrapParts<TParams, TDetails, TState> = {
    hooks,
    renderCall: original.renderCall,
    renderResult: original.renderResult,
    selfShell: original.renderShell === "self",
    shells: new WeakMap<object, StandardShellState>(),
  };

  return {
    ...original,
    renderShell: "self",

    async execute(...args: Parameters<ToolDefinition<TParams, TDetails, TState>["execute"]>) {
      const ctx = args[4];
      return definitionFor(ctx.cwd).execute(...args);
    },

    renderCall: createCalmRenderCall(parts),
    renderResult: createCalmRenderResult(parts),
  };
}

export function createCalmToolWrapper(hooks: CalmToolWrapperHooks) {
  return function wrap<TParams extends TSchema, TDetails, TState>(
    factory: DefinitionFactory<TParams, TDetails, TState>,
  ): ToolDefinition<TParams, TDetails, TState> {
    return wrapBuiltIn(factory, hooks);
  };
}

export function createCalmWrappedBuiltIns(hooks: CalmToolWrapperHooks): ToolDefinition<any, any, any>[] {
  const wrapBuiltIn = createCalmToolWrapper(hooks);
  // Each wrapBuiltIn() call below has its own concrete TParams/TDetails/TState; the
  // array holding all seven has no single sound instantiation, so it is typed the same
  // way Pi's own ToolDefinition consumers erase this (any, any, any).
  return [
    wrapBuiltIn(createReadToolDefinition),
    wrapBuiltIn(createBashToolDefinition),
    wrapBuiltIn(createEditToolDefinition),
    wrapBuiltIn(createWriteToolDefinition),
    wrapBuiltIn(createGrepToolDefinition),
    wrapBuiltIn(createFindToolDefinition),
    wrapBuiltIn(createLsToolDefinition),
  ];
}
