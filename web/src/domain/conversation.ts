/** 对话领域模型 —— 与 gateway 解耦的纯类型。 */

export type TurnStatus = "pending" | "running" | "completed" | "failed" | "canceled";

export interface Turn {
  readonly runId: string;
  readonly traceId: string;
  readonly question: string;
  readonly mode: string;
  readonly status: TurnStatus;
  readonly answer: string;
  readonly createdAt: number;
}

export interface Conversation {
  readonly id: string;
  readonly title: string;
  readonly turns: readonly Turn[];
  readonly createdAt: number;
}

export function conversationTitle(firstQuestion: string): string {
  const trimmed = firstQuestion.trim().replace(/\s+/g, " ");
  if (!trimmed) return "新对话";
  return trimmed.length <= 32 ? trimmed : `${trimmed.slice(0, 32)}…`;
}

export function createConversation(id: string, title?: string): Conversation {
  return {
    id,
    title: title?.trim() || "新对话",
    turns: [],
    createdAt: Date.now(),
  };
}

export function createTurn(
  runId: string,
  traceId: string,
  question: string,
  mode: string,
): Turn {
  return {
    runId,
    traceId,
    question,
    mode,
    status: "pending",
    answer: "",
    createdAt: Date.now(),
  };
}
