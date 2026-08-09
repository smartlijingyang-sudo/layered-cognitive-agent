import type { Message } from "../../projectors/message-types";
import { ThinkingPanel } from "../turn/ThinkingPanel";
import { ToolCallCard } from "../turn/ToolCallCard";
import { SandboxPanel } from "../turn/SandboxPanel";
import { toThinkingBlock, toToolBlock, toSandboxBlock } from "./message-block-adapters";
import { CastingMessage } from "./messages/CastingMessage";
import { DelegationMessage } from "./messages/DelegationMessage";
import { SynthesisMessage } from "./messages/SynthesisMessage";
import { AnswerMessage } from "./messages/AnswerMessage";
import { ErrorMessage } from "./messages/ErrorMessage";
import { InsightMessage } from "./messages/InsightMessage";

export function MessageRenderer({ message }: { readonly message: Message }) {
  switch (message.kind) {
    case "thinking":
      return <ThinkingPanel block={toThinkingBlock(message)} />;
    case "tool_call":
      return <ToolCallCard block={toToolBlock(message)} />;
    case "sandbox":
      return <SandboxPanel block={toSandboxBlock(message)} />;
    case "casting":
      return <CastingMessage message={message} />;
    case "delegation":
      return <DelegationMessage message={message} />;
    case "synthesis":
      return <SynthesisMessage message={message} />;
    case "answer":
      return <AnswerMessage message={message} />;
    case "error":
      return <ErrorMessage message={message} />;
    case "insight":
      return <InsightMessage message={message} />;
    default:
      return null;
  }
}
