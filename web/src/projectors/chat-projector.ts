import type { StampedEvent } from "../contracts/stamped";
import { extractUserFacingAnswer } from "../lib/extract-decision-text";
import { EMPTY_CHAT_STATE, type ChatState, type RunPhase } from "./types";

/** 面向用户的终态动作 — 其 StepTextDelta 可提交到对话主线（answer-delta 投影层）。 */
export const USER_FACING_TERMINAL_ACTIONS = new Set(["respond", "stop", "ask_human"]);

interface StepBuffer {
  readonly deltas: Map<number, string>;
}

interface ChatProjectorInternal extends ChatState {
  readonly pendingSteps: ReadonlyMap<string, StepBuffer>;
  /** 已确认落盘的回答（不含当前 step 流式预览）。 */
  readonly committedAnswer: string;
}

function phaseFromStatus(status: ChatState["status"], prev: RunPhase): RunPhase {
  if (status === "failed") return "failed";
  if (status === "completed") return "completed";
  if (status === "running") return prev === "idle" ? "casting" : prev;
  return "idle";
}

function stepBufferKey(runId: string, step: number): string {
  return `${runId}:${step}`;
}

function orderedDeltaText(buffer: StepBuffer): readonly string[] {
  return [...buffer.deltas.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, text]) => text);
}

function appendBuffer(
  pending: ReadonlyMap<string, StepBuffer>,
  runId: string,
  step: number,
  seq: number,
  textDelta: string,
): ReadonlyMap<string, StepBuffer> {
  const key = stepBufferKey(runId, step);
  const prev = pending.get(key) ?? { deltas: new Map() };
  const nextDeltas = new Map(prev.deltas);
  nextDeltas.set(seq, textDelta);
  const next = new Map(pending);
  next.set(key, { deltas: nextDeltas });
  return next;
}

function commitStepBuffer(
  state: ChatProjectorInternal,
  runId: string,
  step: number,
): ChatProjectorInternal {
  const key = stepBufferKey(runId, step);
  const buffer = state.pendingSteps.get(key);
  if (!buffer) return state;
  const deltaList = orderedDeltaText(buffer);
  const raw = deltaList.join("");
  const text = extractUserFacingAnswer(raw) ?? raw;
  const nextPending = new Map(state.pendingSteps);
  nextPending.delete(key);
  const committedAnswer = state.committedAnswer
    ? `${state.committedAnswer}${text}`
    : text;
  return {
    ...state,
    pendingSteps: nextPending,
    committedAnswer,
    answerDeltas: text ? [...state.answerDeltas, text] : [...state.answerDeltas],
    answer: committedAnswer,
  };
}

function previewFromPendingStep(
  state: ChatProjectorInternal,
  runId: string,
  step: number,
): string | null {
  const buffer = state.pendingSteps.get(stepBufferKey(runId, step));
  if (!buffer) return null;
  return extractUserFacingAnswer(orderedDeltaText(buffer).join(""), { allowPartial: true });
}

function discardStepBuffer(
  state: ChatProjectorInternal,
  runId: string,
  step: number,
): ChatProjectorInternal {
  const key = stepBufferKey(runId, step);
  if (!state.pendingSteps.has(key)) return state;
  const nextPending = new Map(state.pendingSteps);
  nextPending.delete(key);
  return {
    ...state,
    pendingSteps: nextPending,
    answer: state.committedAnswer,
    answerDeltas: state.committedAnswer ? [state.committedAnswer] : [],
  };
}

function commitAllRunBuffers(
  state: ChatProjectorInternal,
  runId: string,
): ChatProjectorInternal {
  let next = state;
  for (const key of state.pendingSteps.keys()) {
    if (key.startsWith(`${runId}:`)) {
      const step = Number(key.slice(runId.length + 1));
      next = commitStepBuffer(next, runId, step);
    }
  }
  return next;
}

function finalizeAnswerText(raw: string): string {
  return extractUserFacingAnswer(raw) ?? raw;
}

const EMPTY_INTERNAL: ChatProjectorInternal = {
  ...EMPTY_CHAT_STATE,
  pendingSteps: new Map(),
  committedAnswer: "",
};

/** 对话主线：问题 + 已确认 answer-delta 流 + 终态 output_text。 */
export function reduceChat(state: ChatProjectorInternal, stamped: StampedEvent): ChatProjectorInternal {
  const e = stamped.event;
  const runId = stamped.scope.run_id;

  switch (e.type) {
    case "CastingStarted":
      return { ...state, status: "running", phase: "casting" };
    case "CastingCompleted":
      return { ...state, status: "running", phase: "collaborating" };
    case "CastingFailed":
      return {
        ...state,
        status: "failed",
        phase: "failed",
        errorMessage: e.error || "自动组队失败",
      };
    case "TeamRunStarted":
      return {
        ...state,
        status: "running",
        phase: "collaborating",
        teamId: e.team_id,
        question: e.objective_preview || state.question,
      };
    case "TeamRunFinished": {
      const committed = commitAllRunBuffers(state, runId);
      const status = e.status === "completed" ? "completed" : "failed";
      const answer = finalizeAnswerText(e.output_text || committed.answer);
      return {
        ...committed,
        status,
        phase: status === "completed" ? "completed" : "failed",
        committedAnswer: answer,
        answer,
        errorMessage: e.error || committed.errorMessage,
      };
    }
    case "AgentRunStarted":
      if (!state.question && e.objective_preview) {
        return { ...state, question: e.objective_preview, status: "running", phase: "collaborating" };
      }
      return { ...state, status: "running", phase: state.phase === "casting" ? "collaborating" : state.phase };
    case "AgentRunFinished": {
      const committed = commitAllRunBuffers(state, runId);
      if (e.output_text) {
        const status = e.status === "completed" ? "completed" : "failed";
        const answer = finalizeAnswerText(e.output_text);
        return {
          ...committed,
          committedAnswer: answer,
          answer,
          status,
          phase: status === "completed" ? "completed" : "failed",
        };
      }
      if (!committed.answer) {
        const status = e.status === "completed" ? "completed" : "failed";
        return {
          ...committed,
          status,
          phase: phaseFromStatus(status, committed.phase),
        };
      }
      return committed;
    }
    case "SynthesisCompleted": {
      const committed = commitAllRunBuffers(state, runId);
      const answer = finalizeAnswerText(e.output_text || committed.answer);
      return {
        ...committed,
        phase: "synthesizing",
        committedAnswer: answer,
        answer,
      };
    }
    case "StepTextDelta": {
      const pendingSteps = appendBuffer(state.pendingSteps, runId, e.step, e.seq, e.text_delta);
      const preview = previewFromPendingStep({ ...state, pendingSteps }, runId, e.step);
      if (!preview) {
        return { ...state, pendingSteps };
      }
      const answer = state.committedAnswer ? `${state.committedAnswer}${preview}` : preview;
      return { ...state, pendingSteps, answer, answerDeltas: [preview] };
    }
    case "DecisionMade":
      if (USER_FACING_TERMINAL_ACTIONS.has(e.action_type)) {
        return commitStepBuffer(state, runId, e.step);
      }
      return discardStepBuffer(state, runId, e.step);
    default:
      return state;
  }
}

export class ChatProjector {
  private state: ChatProjectorInternal = EMPTY_INTERNAL;

  start(question: string): void {
    this.state = { ...EMPTY_INTERNAL, question, status: "running", phase: "casting" };
  }

  onEvent(stamped: StampedEvent): ChatState {
    this.state = reduceChat(this.state, stamped);
    return this.snapshot();
  }

  snapshot(): ChatState {
    const { pendingSteps: _pending, committedAnswer: _committed, ...publicState } = this.state;
    return publicState;
  }
}

/** 假流式 fallback：无真实 delta 时按句切分（ADR-0041 过渡态）。 */
export function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[。！？.!?])\s*/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** 优先消费真实 delta 序列，否则回退 splitSentences。 */
export function revealChunks(text: string, deltas: readonly string[]): readonly string[] {
  return deltas.length > 0 ? deltas : splitSentences(text);
}
