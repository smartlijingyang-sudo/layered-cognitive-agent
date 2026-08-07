import type { StampedEvent } from "../contracts/stamped";
import { EMPTY_CHAT_STATE, type ChatState } from "./types";

/** 对话主线：问题 + TeamRunFinished.output_preview 打字机落地。 */
export function reduceChat(state: ChatState, stamped: StampedEvent): ChatState {
  const e = stamped.event;
  switch (e.type) {
    case "TeamRunStarted":
      return {
        ...state,
        status: "running",
        teamId: e.team_id,
        question: e.objective_preview || state.question,
      };
    case "TeamRunFinished":
      return {
        ...state,
        status: e.status === "completed" ? "completed" : "failed",
        answer: e.output_preview || state.answer,
      };
    case "AgentRunStarted":
      if (!state.question && e.objective_preview) {
        return { ...state, question: e.objective_preview, status: "running" };
      }
      return { ...state, status: "running" };
    case "AgentRunFinished":
      if (!state.answer && e.output_preview) {
        return {
          ...state,
          answer: e.output_preview,
          status: e.status === "completed" ? "completed" : "failed",
        };
      }
      return state;
    default:
      return state;
  }
}

export class ChatProjector {
  private state: ChatState = EMPTY_CHAT_STATE;

  start(question: string): void {
    this.state = { question, answer: "", status: "running" };
  }

  onEvent(stamped: StampedEvent): ChatState {
    this.state = reduceChat(this.state, stamped);
    return this.state;
  }

  snapshot(): ChatState {
    return this.state;
  }
}

/** 逐句打字机（真 token 流接入前顶一顶）。 */
export function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[。！？.!?])\s*/)
    .map((s) => s.trim())
    .filter(Boolean);
}
