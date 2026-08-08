/** 对话领域模型 —— 与 gateway 解耦的纯类型。 */

import type { GeneratedFile, LocalAttachment } from "./generated-file";

export type { GeneratedFile, LocalAttachment };
export type { AttachmentRef } from "./generated-file";

export type TurnStatus = "pending" | "running" | "completed" | "failed" | "canceled";

export interface Turn {
  readonly runId: string;
  readonly traceId: string;
  readonly question: string;
  readonly mode: string;
  readonly status: TurnStatus;
  readonly answer: string;
  readonly answerDeltas?: readonly string[];
  /** Agent-generated file products (A2A file-part shape). Optional until backend lands. */
  readonly files?: readonly GeneratedFile[];
  /** User attachments associated with this turn (local and/or uploaded refs). */
  readonly attachments?: readonly LocalAttachment[];
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
    answerDeltas: [],
    createdAt: Date.now(),
  };
}
