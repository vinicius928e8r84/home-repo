import type { AssistantMessageComponent as PiAssistantMessageComponent } from "@earendil-works/pi-coding-agent";
import * as PiCodingAgent from "@earendil-works/pi-coding-agent";
import { calmTextIsSubstantive } from "./fm-calm-preservation.ts";
import { calmPresentationHides } from "./fm-calm-visibility.ts";

type AssistantMessage = Parameters<PiAssistantMessageComponent["updateContent"]>[0];

type AssistantMessagePresentationState = {
  hiddenThinkingLabel: string;
  hideThinkingBlock: boolean;
  lastMessage?: AssistantMessage;
};

type CalmAssistantLayoutPatch = {
  hidesThinking: () => boolean;
  hidesWorkingNote: () => boolean;
};

function isMidTurnAssistantMessage(message: AssistantMessage): boolean {
  if (message.stopReason === "toolUse") return true;
  return (
    message.stopReason === "length" &&
    message.content.some((block) => block.type === "toolCall")
  );
}

const CALM_ASSISTANT_LAYOUT_PATCH = Symbol.for(
  "firstmate:calm-assistant-layout:pi-0.81.1",
);

export function installCalmAssistantLayout(): void {
  const registry = globalThis as typeof globalThis & {
    [key: symbol]: CalmAssistantLayoutPatch | undefined;
  };
  const hidesThinking = (): boolean => calmPresentationHides("assistant-thinking");
  const hidesWorkingNote = (): boolean => calmPresentationHides("assistant-working-note");
  const installed = registry[CALM_ASSISTANT_LAYOUT_PATCH];
  if (installed) {
    installed.hidesThinking = hidesThinking;
    installed.hidesWorkingNote = hidesWorkingNote;
    return;
  }

  const patch: CalmAssistantLayoutPatch = { hidesThinking, hidesWorkingNote };
  const AssistantMessageComponent = PiCodingAgent.AssistantMessageComponent;
  if (typeof AssistantMessageComponent !== "function") {
    throw new Error("Firstmate Calm requires Pi AssistantMessageComponent");
  }
  const originalUpdateContent = AssistantMessageComponent.prototype.updateContent;
  if (typeof originalUpdateContent !== "function") {
    throw new Error("Firstmate Calm requires Pi AssistantMessageComponent.updateContent");
  }

  AssistantMessageComponent.prototype.updateContent = function (
    message: AssistantMessage,
  ): void {
    const state = this as unknown as AssistantMessagePresentationState;
    const hideThinking =
      state.hiddenThinkingLabel === "" &&
      state.hideThinkingBlock &&
      patch.hidesThinking();
    const hideWorkingNote =
      patch.hidesWorkingNote() &&
      isMidTurnAssistantMessage(message) &&
      message.content.some(
        (block) => block.type === "text" && !calmTextIsSubstantive(block.text),
      );
    const presentationMessage =
      hideThinking || hideWorkingNote
        ? {
            ...message,
            content: message.content.filter(
              (block) =>
                !(hideThinking && block.type === "thinking") &&
                !(
                  hideWorkingNote &&
                  block.type === "text" &&
                  !calmTextIsSubstantive(block.text)
                ),
            ),
          }
        : message;

    originalUpdateContent.call(this, presentationMessage);
    if (presentationMessage !== message) state.lastMessage = message;
  };

  registry[CALM_ASSISTANT_LAYOUT_PATCH] = patch;
}
