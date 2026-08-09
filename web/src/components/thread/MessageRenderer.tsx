import type { Message } from "../../projectors/message-types";
import { ThinkingPanel } from "../turn/ThinkingPanel";
import { ToolCallCard } from "../turn/ToolCallCard";
import { toExecOutputBlock, toThinkingBlock, toToolBlock } from "./message-block-adapters";
import { CastingMessage } from "./messages/CastingMessage";
import { DelegationMessage } from "./messages/DelegationMessage";
import { SynthesisMessage } from "./messages/SynthesisMessage";
import { AnswerMessage } from "./messages/AnswerMessage";
import { ErrorMessage } from "./messages/ErrorMessage";
import { InsightMessage } from "./messages/InsightMessage";
import { filesFromToolInvoked } from "../../lib/parse-generated-file";
import { GeneratedFileList } from "../shared/GeneratedFileCard";

export function MessageRenderer({ message }: { readonly message: Message }) {
  switch (message.kind) {
    case "thinking":
      return <ThinkingPanel block={toThinkingBlock(message)} />;
    case "tool_call": {
      const files = filesFromToolInvoked({
        toolName: message.metadata?.toolName ?? "",
        resultPreview: message.metadata?.resultPreview ?? "",
        ok: message.metadata?.ok ?? message.status !== "error",
        files: message.metadata?.files,
      });
      return (
        <>
          <ToolCallCard block={toToolBlock(message)} sandbox={toExecOutputBlock(message)} />
          {files.length > 0 ? (
            <div className="pl-1">
              <GeneratedFileList files={files} />
            </div>
          ) : null}
        </>
      );
    }
    case "sandbox":
      // Legacy journal rows — output is merged into tool_call in MessageProjector.
      return null;
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
