import * as PiCodingAgent from "@earendil-works/pi-coding-agent";
import { calmPresentationHides } from "./fm-calm-visibility.ts";
import { isFirstmateOperationalPresentationText } from "./fm-operational-input.ts";

type QueuedMessages = {
  steering: string[];
  followUp: string[];
};
type CompactionQueuedMessage = {
  text: string;
  mode: string;
};
type RetainingSession = {
  getSteeringMessages(): readonly string[];
  getFollowUpMessages(): readonly string[];
  clearQueue(): QueuedMessages;
  _queueSteer(text: string): unknown;
  _queueFollowUp(text: string): unknown;
  waitForIdle(): Promise<void>;
  sendUserMessage(content: string): Promise<void>;
  readonly isIdle: boolean;
};
type PendingRowsHost = {
  session: unknown;
  compactionQueuedMessages: CompactionQueuedMessage[];
  showStatus?(message: string): void;
  showWarning?(message: string): void;
  updatePendingMessagesDisplay(): void;
};
type RestoreOptions = {
  abort?: boolean;
  currentText?: string;
};
type InteractiveModePendingPrototype = {
  getAllQueuedMessages(this: PendingRowsHost): QueuedMessages;
  updatePendingMessagesDisplay(this: PendingRowsHost): void;
  clearAllQueues(this: PendingRowsHost): QueuedMessages;
  restoreQueuedMessagesToEditor(this: PendingRowsHost, options?: RestoreOptions): number;
};
type CalmPendingOperationalLayoutPatch = {
  hidesOperationalInput: () => boolean;
  isOperationalInput: (text: string) => boolean;
  refresh: () => void;
};
type Restoring = {
  session: RetainingSession;
  retains: (text: string) => boolean;
  keptInAgentQueue: number;
};

export const CALM_QUEUE_RETENTION_SESSION_METHODS = [
  "getSteeringMessages",
  "getFollowUpMessages",
  "clearQueue",
  "_queueSteer",
  "_queueFollowUp",
  "waitForIdle",
  "sendUserMessage",
] as const;

export const CALM_QUEUED_ROWS_UNSUPPORTED_WARNING =
  "Firstmate Calm: this Pi session cannot keep queued messages across Escape, so queued Firstmate rows stay visible.";
export const CALM_SUPERVISION_CONTINUES_NOTICE =
  "Firstmate supervision continues in a new turn.";

const CALM_PENDING_OPERATIONAL_LAYOUT_PATCH = Symbol.for(
  "firstmate:calm-pending-operational-layout:pi-0.87.1",
);

function settle(queued: unknown): void {
  void Promise.resolve(queued).catch(() => {});
}

type PendingState = {
  readonly patch: CalmPendingOperationalLayoutPatch;
  readonly retentionBySession: WeakMap<object, boolean>;
  lastHost?: PendingRowsHost;
  hidden?: { session: object; texts: Set<string> };
  hidingInto?: Set<string>;
  restoring?: Restoring;
};

function createPendingState(hidesOperationalInput: () => boolean): PendingState {
  const state: PendingState = {
    patch: {
      hidesOperationalInput,
      isOperationalInput: isFirstmateOperationalPresentationText,
      refresh: () => state.lastHost?.updatePendingMessagesDisplay(),
    },
    retentionBySession: new WeakMap<object, boolean>(),
  };
  return state;
}

function capturePendingOriginals(
  prototype: InteractiveModePendingPrototype,
): InteractiveModePendingPrototype {
  const originals: InteractiveModePendingPrototype = {
    getAllQueuedMessages: prototype.getAllQueuedMessages,
    updatePendingMessagesDisplay: prototype.updatePendingMessagesDisplay,
    clearAllQueues: prototype.clearAllQueues,
    restoreQueuedMessagesToEditor: prototype.restoreQueuedMessagesToEditor,
  };
  for (const [name, method] of Object.entries(originals)) {
    if (typeof method !== "function") {
      throw new Error(`Firstmate Calm requires Pi InteractiveMode.${name}`);
    }
  }
  return originals;
}

function supportsRetention(members: Record<string, unknown>, host: PendingRowsHost): boolean {
  return (
    CALM_QUEUE_RETENTION_SESSION_METHODS.every((name) => typeof members[name] === "function") &&
    typeof members.isIdle === "boolean" &&
    Array.isArray(host.compactionQueuedMessages)
  );
}

function warnUnsupported(host: PendingRowsHost): void {
  if (typeof host.showWarning === "function") {
    host.showWarning(CALM_QUEUED_ROWS_UNSUPPORTED_WARNING);
  } else {
    process.stderr.write(`${CALM_QUEUED_ROWS_UNSUPPORTED_WARNING}\n`);
  }
}

function retainingSession(state: PendingState, host: PendingRowsHost): RetainingSession | undefined {
  const session = host.session;
  if (typeof session !== "object" || session === null) return undefined;
  let supported = state.retentionBySession.get(session);
  if (supported === undefined) {
    supported = supportsRetention(session as Record<string, unknown>, host);
    state.retentionBySession.set(session, supported);
    if (!supported) warnUnsupported(host);
  }
  return supported ? (session as RetainingSession) : undefined;
}

function continueWhenSettled(host: PendingRowsHost, session: RetainingSession): void {
  const settled = async (): Promise<boolean> => {
    do {
      await session.waitForIdle();
      await new Promise((resolve) => setTimeout(resolve, 0));
      if (host.session !== session) return false;
    } while (!session.isIdle);
    return true;
  };
  settled()
    .then((idle) => {
      if (!idle) return;
      const { steering, followUp } = session.clearQueue();
      const first = steering.length > 0 ? steering.shift() : followUp.shift();
      if (first === undefined) return;
      for (const text of steering) settle(session._queueSteer(text));
      for (const text of followUp) settle(session._queueFollowUp(text));
      host.showStatus?.(CALM_SUPERVISION_CONTINUES_NOTICE);
      session.sendUserMessage(first).catch(() => settle(session._queueFollowUp(first)));
    })
    .catch(() => {});
}

function patchGetAllQueuedMessages(
  prototype: InteractiveModePendingPrototype,
  original: InteractiveModePendingPrototype["getAllQueuedMessages"],
  state: PendingState,
): void {
  prototype.getAllQueuedMessages = function (this: PendingRowsHost): QueuedMessages {
    const queued = original.call(this);
    const texts = state.hidingInto;
    if (!texts) return queued;
    const stays = (text: string): boolean => {
      if (!state.patch.isOperationalInput(text)) return true;
      texts.add(text);
      return false;
    };
    return {
      ...queued,
      steering: queued.steering.filter(stays),
      followUp: queued.followUp.filter(stays),
    };
  };
}

function patchUpdatePendingMessagesDisplay(
  prototype: InteractiveModePendingPrototype,
  original: InteractiveModePendingPrototype["updatePendingMessagesDisplay"],
  state: PendingState,
): void {
  prototype.updatePendingMessagesDisplay = function (this: PendingRowsHost): void {
    state.lastHost = this;
    if (!state.patch.hidesOperationalInput() || !retainingSession(state, this)) {
      state.hidden = undefined;
      original.call(this);
      return;
    }
    const texts = new Set<string>();
    state.hidingInto = texts;
    try {
      original.call(this);
    } finally {
      state.hidingInto = undefined;
    }
    state.hidden = texts.size > 0 ? { session: this.session as object, texts } : undefined;
  };
}

function patchClearAllQueues(
  prototype: InteractiveModePendingPrototype,
  original: InteractiveModePendingPrototype["clearAllQueues"],
  state: PendingState,
): void {
  prototype.clearAllQueues = function (this: PendingRowsHost): QueuedMessages {
    const current = state.restoring;
    if (!current) return original.call(this);
    const { session, retains } = current;
    const steering = session.getSteeringMessages().filter(retains);
    const followUp = session.getFollowUpMessages().filter(retains);
    const compaction = this.compactionQueuedMessages.filter((message) => retains(message.text));
    const cleared = original.call(this);
    if (steering.length + followUp.length + compaction.length === 0) return cleared;
    for (const text of steering) settle(session._queueSteer(text));
    for (const text of followUp) settle(session._queueFollowUp(text));
    this.compactionQueuedMessages.push(...compaction);
    current.keptInAgentQueue = steering.length + followUp.length;
    return {
      ...cleared,
      steering: cleared.steering.filter((text) => !retains(text)),
      followUp: cleared.followUp.filter((text) => !retains(text)),
    };
  };
}

function retainsHidden(
  state: PendingState,
  hiddenTexts: Set<string> | undefined,
  hidesNow: boolean,
): (text: string) => boolean {
  const answers = new Map<string, boolean>();
  return (text: string): boolean => {
    if (hiddenTexts?.has(text)) return true;
    if (!hidesNow) return false;
    let answer = answers.get(text);
    if (answer === undefined) {
      answer = state.patch.isOperationalInput(text);
      answers.set(text, answer);
    }
    return answer;
  };
}

function patchRestoreQueuedMessagesToEditor(
  prototype: InteractiveModePendingPrototype,
  original: InteractiveModePendingPrototype["restoreQueuedMessagesToEditor"],
  state: PendingState,
): void {
  prototype.restoreQueuedMessagesToEditor = function (
    this: PendingRowsHost,
    options?: RestoreOptions,
  ): number {
    const hidesNow = state.patch.hidesOperationalInput();
    const hidden = state.hidden;
    const hiddenTexts = hidden && hidden.session === this.session ? hidden.texts : undefined;
    const session = hidesNow || hiddenTexts ? retainingSession(state, this) : undefined;
    if (!session) return original.call(this, options);

    const retains = retainsHidden(state, hiddenTexts, hidesNow);
    const current: Restoring = { session, retains, keptInAgentQueue: 0 };
    state.restoring = current;
    try {
      return original.call(this, options);
    } finally {
      state.restoring = undefined;
      if (current.keptInAgentQueue > 0) continueWhenSettled(this, session);
    }
  };
}

export function installCalmPendingOperationalLayout(): void {
  const registry = globalThis as typeof globalThis & {
    [key: symbol]: CalmPendingOperationalLayoutPatch | undefined;
  };
  const hidesOperationalInput = (): boolean => calmPresentationHides("synthetic-user");
  const installed = registry[CALM_PENDING_OPERATIONAL_LAYOUT_PATCH];
  if (installed) {
    installed.hidesOperationalInput = hidesOperationalInput;
    installed.isOperationalInput = isFirstmateOperationalPresentationText;
    return;
  }

  const InteractiveMode = PiCodingAgent.InteractiveMode;
  if (typeof InteractiveMode !== "function") {
    throw new Error("Firstmate Calm requires Pi InteractiveMode");
  }
  const prototype = InteractiveMode.prototype as unknown as InteractiveModePendingPrototype;
  const originals = capturePendingOriginals(prototype);
  const state = createPendingState(hidesOperationalInput);

  patchGetAllQueuedMessages(prototype, originals.getAllQueuedMessages, state);
  patchUpdatePendingMessagesDisplay(prototype, originals.updatePendingMessagesDisplay, state);
  patchClearAllQueues(prototype, originals.clearAllQueues, state);
  patchRestoreQueuedMessagesToEditor(prototype, originals.restoreQueuedMessagesToEditor, state);

  registry[CALM_PENDING_OPERATIONAL_LAYOUT_PATCH] = state.patch;
}

export function refreshCalmPendingOperationalRows(): void {
  const registry = globalThis as typeof globalThis & {
    [key: symbol]: CalmPendingOperationalLayoutPatch | undefined;
  };
  registry[CALM_PENDING_OPERATIONAL_LAYOUT_PATCH]?.refresh();
}
