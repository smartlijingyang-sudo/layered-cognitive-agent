/**
 * MessageProjector — projects ALL journal event types into Message[].
 *
 * Design:
 * - Internal messages use a mutable `buffer` field for streaming accumulation.
 * - `buildTurn()` creates an immutable snapshot with sorted messages (buffer stripped).
 * - For StepTextDelta, `stepChannelKey` from step-text-buffer is used for buffering.
 * - USER_FACING_TERMINAL_ACTIONS determines which DecisionMade events commit answer messages.
 */

import type { StampedEvent } from "../contracts/stamped";
import { stepChannelKey } from "../lib/step-text-buffer";
import { sortMessages } from "./message-sort";
import type { Message, MessageKind, MessageMetadata, Turn } from "./message-types";

/** User-facing terminal actions — their StepTextDelta commits to the answer line. */
export const USER_FACING_TERMINAL_ACTIONS = new Set(["respond", "stop", "ask_human"]);

/* ── Internal mutable types ─────────────────────────────────────── */

/** Mutable mirror of Message — drops `readonly` for internal accumulation. */
interface MutableMessage {
  id: string;
  kind: MessageKind;
  agentRole?: string;
  content: string;
  streaming: boolean;
  status: "running" | "done" | "error";
  startedAt: number;
  completedAt?: number;
  metadata?: MessageMetadata;
  buffer: string;
}

interface InternalState {
  messages: Map<string, MutableMessage>;
  /** Accumulates streaming text keyed by message id. */
  buffers: Map<string, string>;
  /** Step-text deltas keyed by stepChannelKey(runId, step, channel). */
  stepBuffers: Map<string, string>;
  /** Live stdout/stderr keyed by tool invocation_id (LobeHub tool_state). */
  execBuffers: Map<string, { stdout: string; stderr: string; sealed: boolean }>;
  turnStatus: "running" | "completed" | "failed";
  turnMode: "solo" | "team";
  teamId?: string;
  question: string;
  startedAt?: number;
  completedAt?: number;
  errorMessage?: string;
  seq: number;
}

/* ── Helpers ────────────────────────────────────────────────────── */

function createEmptyState(): InternalState {
  return {
    messages: new Map(),
    buffers: new Map(),
    stepBuffers: new Map(),
    execBuffers: new Map(),
    turnStatus: "running",
    turnMode: "solo",
    question: "",
    seq: 0,
  };
}

function nextSeq(state: InternalState): number {
  return state.seq++;
}

function makeMsg(
  id: string,
  kind: MessageKind,
  ts: number,
  overrides: Partial<MutableMessage> = {},
): MutableMessage {
  return {
    id,
    kind,
    content: "",
    streaming: true,
    status: "running",
    startedAt: ts,
    buffer: "",
    ...overrides,
  };
}

/** Immutable snapshot — strip internal `buffer` field. */
function freeze(msg: MutableMessage): Message {
  const { buffer: _, ...rest } = msg;
  return rest;
}

function toolMessageKey(invocationId: string, toolName: string, fallback: string): string {
  if (invocationId) return `tool:${invocationId}`;
  return `tool:${toolName}:${fallback}`;
}

function applyExecBufferToTool(msg: MutableMessage, buf: { stdout: string; stderr: string; sealed: boolean }): void {
  msg.metadata = {
    ...msg.metadata,
    stdout: buf.stdout || undefined,
    stderr: buf.stderr || undefined,
    sealed: buf.sealed,
  };
}

function findToolByInvocation(state: InternalState, invocationId: string): MutableMessage | undefined {
  if (!invocationId) return undefined;
  for (const msg of state.messages.values()) {
    if (msg.kind === "tool_call" && msg.metadata?.invocationId === invocationId) {
      return msg;
    }
  }
  return undefined;
}

function upsertExecBuffer(
  state: InternalState,
  invocationId: string,
  stream: string,
  delta: string,
): { stdout: string; stderr: string; sealed: boolean } {
  const prev = state.execBuffers.get(invocationId) ?? { stdout: "", stderr: "", sealed: false };
  if (prev.sealed) return prev;
  const next = {
    ...prev,
    stdout: stream === "stdout" ? prev.stdout + delta : prev.stdout,
    stderr: stream === "stderr" ? prev.stderr + delta : prev.stderr,
  };
  state.execBuffers.set(invocationId, next);
  return next;
}

/* ── MessageProjector ───────────────────────────────────────────── */

export class MessageProjector {
  private state: InternalState = createEmptyState();

  /** Reset all state (e.g. between turns). */
  reset(): void {
    this.state = createEmptyState();
  }

  /** Feed one journal event into the projector. */
  onEvent(stamped: StampedEvent): void {
    const s = this.state;
    const e = stamped.event;
    const ts = stamped.ts;
    const runId = stamped.scope.run_id;
    const role = stamped.scope.agent_role;

    switch (e.type) {
      /* ── Casting ─────────────────────────────────────────────── */
      case "CastingStarted": {
        const id = "casting";
        s.messages.set(
          id,
          makeMsg(id, "casting", ts, {
            status: "running",
            metadata: { objectivePreview: e.objective_preview },
          }),
        );
        s.startedAt ??= ts;
        break;
      }
      case "CastingCompleted": {
        const msg = s.messages.get("casting");
        if (msg) {
          msg.status = "done";
          msg.streaming = false;
          msg.completedAt = ts;
          msg.metadata = {
            ...msg.metadata,
            governanceKind: e.governance_kind,
            leadRole: e.lead_role,
            selectedRoles: e.selected_roles,
            rationale: e.rationale,
          };
        }
        break;
      }
      case "CastingFailed": {
        const id = `error:casting:${nextSeq(s)}`;
        s.messages.set(
          id,
          makeMsg(id, "error", ts, {
            status: "error",
            streaming: false,
            content: e.error,
            completedAt: ts,
            metadata: { error: e.error },
          }),
        );
        const casting = s.messages.get("casting");
        if (casting) {
          casting.status = "error";
          casting.streaming = false;
          casting.completedAt = ts;
        }
        break;
      }

      /* ── Thinking (Reasoning) ────────────────────────────────── */
      case "ReasoningDelta": {
        const id = `thinking:${runId}:${role}`;
        let msg = s.messages.get(id);
        if (!msg) {
          msg = makeMsg(id, "thinking", ts, { agentRole: role, streaming: true });
          s.messages.set(id, msg);
        }
        const bufKey = `thinking:${runId}:${role}`;
        const buf = (s.buffers.get(bufKey) ?? "") + e.text_delta;
        s.buffers.set(bufKey, buf);
        msg.content = buf;
        s.startedAt ??= ts;
        break;
      }
      case "ReasoningCompleted": {
        const id = `thinking:${runId}:${role}`;
        const msg = s.messages.get(id);
        if (msg) {
          msg.streaming = false;
          msg.status = "done";
          msg.completedAt = ts;
          msg.metadata = { ...msg.metadata, durationMs: e.duration_ms };
          if (e.content_preview?.trim() && !msg.content.trim()) {
            msg.content = e.content_preview;
          }
        }
        break;
      }

      /* ── Tool calls ──────────────────────────────────────────── */
      case "ToolStarted": {
        const id = toolMessageKey(e.invocation_id, e.tool_name, `${ts}:${nextSeq(s)}`);
        const msg = makeMsg(id, "tool_call", ts, {
          agentRole: role || undefined,
          metadata: {
            toolName: e.tool_name,
            argumentsPreview: e.arguments_preview,
            invocationId: e.invocation_id,
          },
        });
        s.messages.set(id, msg);
        const pending = s.execBuffers.get(e.invocation_id);
        if (pending) {
          applyExecBufferToTool(msg, pending);
        }
        s.startedAt ??= ts;
        break;
      }
      case "ToolInvoked": {
        const id = toolMessageKey(e.invocation_id, e.tool_name, `${ts}:${s.seq}`);
        let msg = s.messages.get(id);
        if (!msg) {
          const fallbackId = toolMessageKey(e.invocation_id, e.tool_name, `invoked:${nextSeq(s)}`);
          msg = makeMsg(fallbackId, "tool_call", ts, {
            agentRole: role || undefined,
          });
          s.messages.set(fallbackId, msg);
        }
        msg.status = e.ok ? "done" : "error";
        msg.streaming = false;
        msg.completedAt = ts;
        msg.content = e.result_preview;
        const execBuf = s.execBuffers.get(e.invocation_id) ?? {
          stdout: "",
          stderr: "",
          sealed: false,
        };
        execBuf.sealed = true;
        s.execBuffers.set(e.invocation_id, execBuf);
        applyExecBufferToTool(msg, execBuf);
        msg.metadata = {
          ...msg.metadata,
          toolName: e.tool_name,
          argumentsPreview: e.arguments_preview,
          resultPreview: e.result_preview,
          latencyMs: e.latency_ms,
          ok: e.ok,
          error: e.error || undefined,
          invocationId: e.invocation_id,
          files: e.files?.length ? e.files : msg.metadata?.files,
          sealed: true,
        };
        break;
      }

      /* ── Execution output (merged into tool_call — LobeHub tool_state) ─ */
      case "SandboxOutputDelta": {
        const buf = upsertExecBuffer(s, e.invocation_id, e.stream, e.text_delta);
        const tool = findToolByInvocation(s, e.invocation_id);
        if (tool) {
          applyExecBufferToTool(tool, buf);
        }
        s.startedAt ??= ts;
        break;
      }

      /* ── Delegation ──────────────────────────────────────────── */
      case "DelegationIssued": {
        const id = `delegation:${e.delegation_id}`;
        s.messages.set(
          id,
          makeMsg(id, "delegation", ts, {
            agentRole: e.caller_role || role || undefined,
            metadata: {
              delegationId: e.delegation_id,
              calleeRole: e.callee_role,
              fromRole: e.caller_role || undefined,
              subtaskPreview: e.subtask_preview,
            },
          }),
        );
        s.startedAt ??= ts;
        break;
      }
      case "DelegationCompleted": {
        const id = `delegation:${e.delegation_id}`;
        const msg = s.messages.get(id);
        if (msg) {
          msg.status = e.ok ? "done" : "error";
          msg.streaming = false;
          msg.completedAt = ts;
          msg.content = e.output_text;
          msg.metadata = { ...msg.metadata, resultPreview: e.output_text };
        } else {
          // Orphan completion — create a done message
          s.messages.set(
            id,
            makeMsg(id, "delegation", ts, {
              status: e.ok ? "done" : "error",
              streaming: false,
              content: e.output_text,
              completedAt: ts,
              metadata: { delegationId: e.delegation_id, resultPreview: e.output_text },
            }),
          );
        }
        break;
      }

      /* ── Answer (StepTextDelta + DecisionMade) ───────────────── */
      case "StepTextDelta": {
        const channel = e.channel || "decision";
        const id = `answer:${runId}:${e.step}`;
        let msg = s.messages.get(id);
        if (!msg) {
          msg = makeMsg(id, "answer", ts, { streaming: true });
          s.messages.set(id, msg);
        }
        const sKey = stepChannelKey(runId, e.step, channel);
        const prev = s.stepBuffers.get(sKey) ?? "";
        s.stepBuffers.set(sKey, prev + e.text_delta);

        // Aggregate all channels for this step into message content
        const decisionBuf = s.stepBuffers.get(stepChannelKey(runId, e.step, "decision")) ?? "";
        const answerBuf = s.stepBuffers.get(stepChannelKey(runId, e.step, "answer")) ?? "";
        msg.content = decisionBuf + answerBuf;
        s.startedAt ??= ts;
        break;
      }
      case "DecisionMade": {
        if (!USER_FACING_TERMINAL_ACTIONS.has(e.action_type)) break;
        const id = `answer:${runId}:${e.step}`;
        const msg = s.messages.get(id);
        if (msg) {
          msg.streaming = false;
          msg.status = "done";
          msg.completedAt = ts;
          // Canonical response_text takes priority over accumulated buffer
          msg.content = e.response_text?.trim() || msg.content;
        } else {
          // No prior StepTextDelta — create from response_text directly
          if (e.response_text?.trim()) {
            s.messages.set(
              id,
              makeMsg(id, "answer", ts, {
                streaming: false,
                status: "done",
                content: e.response_text,
                completedAt: ts,
              }),
            );
          }
        }
        break;
      }

      /* ── Synthesis ───────────────────────────────────────────── */
      case "SynthesisCompleted": {
        const id = `synthesis:${runId}`;
        const existing = s.messages.get(id);
        if (existing) {
          existing.status = "done";
          existing.streaming = false;
          existing.completedAt = ts;
          existing.content = e.output_text;
          existing.metadata = {
            ...existing.metadata,
            method: e.method,
            candidateCount: e.candidate_count,
          };
        } else {
          s.messages.set(
            id,
            makeMsg(id, "synthesis", ts, {
              status: "done",
              streaming: false,
              content: e.output_text,
              completedAt: ts,
              metadata: { method: e.method, candidateCount: e.candidate_count },
            }),
          );
        }
        break;
      }

      /* ── Insight ─────────────────────────────────────────────── */
      case "RunInsight": {
        const id = `insight:${runId}:${nextSeq(s)}`;
        s.messages.set(
          id,
          makeMsg(id, "insight", ts, {
            status: "done",
            streaming: false,
            content: e.summary,
            completedAt: ts,
            metadata: { insightKind: e.kind, summary: e.summary, detail: e.detail },
          }),
        );
        break;
      }

      /* ── Run containers (status updates, no direct messages) ── */
      case "TeamRunStarted": {
        s.turnMode = "team";
        s.teamId = e.team_id;
        s.question = e.objective_preview || s.question;
        s.turnStatus = "running";
        s.startedAt ??= ts;
        break;
      }
      case "AgentRunStarted": {
        s.turnStatus = "running";
        s.startedAt ??= ts;
        if (!s.question && e.objective_preview) {
          s.question = e.objective_preview;
        }
        break;
      }
      case "TeamRunFinished": {
        s.turnStatus = e.status === "completed" ? "completed" : "failed";
        s.completedAt = ts;
        if (e.error) s.errorMessage = e.error;
        break;
      }
      case "AgentRunFinished": {
        if (e.status !== "completed") {
          s.turnStatus = "failed";
          s.completedAt = ts;
        }
        if (e.error) s.errorMessage = e.error;
        break;
      }

      /* ── LLM / Activity (no dedicated message kind) ─────────── */
      case "LlmCallStarted":
      case "RunActivity":
        // These update activity indicators in other projectors;
        // no dedicated Message kind in the message projector.
        break;

      default:
        break;
    }
  }

  /** Create an immutable Turn snapshot with sorted, frozen messages. */
  buildTurn(turnId: string): Turn {
    const msgs = sortMessages([...this.state.messages.values()].map(freeze));
    return {
      id: turnId,
      runId: "",
      question: this.state.question,
      mode: this.state.turnMode,
      messages: msgs,
      status: this.state.turnStatus,
      startedAt: this.state.startedAt ?? 0,
      completedAt: this.state.completedAt,
      teamId: this.state.teamId,
      errorMessage: this.state.errorMessage,
    };
  }

  /** Read-only access to current frozen messages (sorted). */
  getMessages(): readonly Message[] {
    return sortMessages([...this.state.messages.values()].map(freeze));
  }
}

/* ── Shared utilities (moved from chat-projector) ───────────────── */

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
