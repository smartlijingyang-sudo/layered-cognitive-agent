import type { Message } from "../../projectors/message-types";
import type { SandboxBlock, ThinkingBlock, ToolBlock } from "../../projectors/types";

/** Convert a thinking-kind Message into a ThinkingBlock for ThinkingPanel. */
export function toThinkingBlock(msg: Message): ThinkingBlock {
  return {
    kind: "thinking",
    id: msg.id,
    status: msg.streaming ? "running" : "done",
    content: msg.content,
    durationMs: msg.metadata?.durationMs,
  };
}

/** Convert a tool_call-kind Message into a ToolBlock for ToolCallCard. */
export function toToolBlock(msg: Message): ToolBlock {
  return {
    kind: "tool",
    id: msg.id,
    status: msg.status,
    toolName: msg.metadata?.toolName ?? "",
    argumentsPreview: msg.metadata?.argumentsPreview ?? "",
    resultPreview: msg.metadata?.resultPreview ?? "",
    ok: msg.metadata?.ok,
    latencyMs: msg.metadata?.latencyMs,
    error: msg.metadata?.error,
    invocationId: msg.metadata?.invocationId ?? "",
    agentRole: msg.agentRole,
  };
}

/** Convert a sandbox-kind Message into a SandboxBlock for SandboxPanel. */
export function toSandboxBlock(msg: Message): SandboxBlock {
  return {
    kind: "sandbox",
    id: msg.id,
    status: msg.metadata?.sealed ? "done" : "running",
    invocationId: msg.metadata?.invocationId ?? "",
    stdout: msg.metadata?.stdout ?? "",
    stderr: msg.metadata?.stderr ?? "",
    sealed: msg.metadata?.sealed ?? false,
    agentRole: msg.agentRole,
  };
}
