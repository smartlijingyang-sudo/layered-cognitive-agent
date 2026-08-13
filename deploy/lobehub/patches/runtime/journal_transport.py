"""Patch: JournalTransport — Journal live SSE into native StreamingHandler."""

from __future__ import annotations

import re
from collections.abc import Mapping

from deploy.lobehub.engine import PatchContext, PatchMeta
from gateway.runs.wire import WIRE

meta = PatchMeta(
    name="journal_transport",
    description="LCA agent stream via Journal live SSE + native StreamingHandler",
    files=(
        "src/store/chat/agents/transports/JournalTransport.ts",
        "src/store/chat/agents/transports/buildClientRuntimeHost.ts",
    ),
    risk="high",
    category="runtime",
    depends_on=(),
    why="Upstream assumes the browser runs tools; LCA already ran them on the server",
    technical_detail="Replace ClientLLMTransport with JournalTransport that feeds StreamingHandler",
    verify_file="src/store/chat/agents/transports/JournalTransport.ts",
    verify_marker="JournalTransport",
)


def render_wire_ts(wire: Mapping[str, tuple[str, str]]) -> str:
    lines = ["const WIRE: Record<string, readonly [string, string]> = {"]
    for name, (identifier, api_name) in wire.items():
        lines.append(f"  '{name}': ['{identifier}', '{api_name}'],")
    lines.append("};")
    return "\n".join(lines)


def _transport_ts() -> str:
    return _TRANSPORT_TEMPLATE.replace("/* __WIRE__ */", render_wire_ts(WIRE))


_TRANSPORT_TEMPLATE = r"""import type {
  ClassifiedLLMError,
  LLMAttemptExecution,
  LLMAttemptInput,
  LLMAttemptOutput,
  LLMRetryPolicy,
  LLMStreamPayload,
  LLMStreamResult,
  LLMTransport,
} from '@lobechat/agent-runtime';
import type { ChatToolPayload, MessageToolCall } from '@lobechat/types';

import type { ChatStore } from '@/store/chat/store';

import { StreamingHandler } from '../StreamingHandler';
import type { StreamChunk } from '../types/streaming';
import type { ClientRuntimeSession } from './ClientRuntimeStreamSink';

const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
const FIRST_FRAME_MS = 10_000;

/* __WIRE__ */

const MUST_MAP = new Set([
  'ReasoningDelta',
  'StepTextDelta',
  'ToolStarted',
  'SandboxOutputDelta',
  'ToolInvoked',
  'ToolDenied',
  'AgentRunFinished',
  'TeamRunFinished',
]);

type JournalFrame = {
  event: string;
  id?: string;
  seq?: number;
  event_type?: string;
  eventPayload?: Record<string, unknown>;
};

function hopLog(
  hop: string,
  runId: string,
  extra: Record<string, unknown> = {},
): void {
  console.info('lca.hop', { hop, run_id: runId, ...extra });
}

function pickArgs(state: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!state) return {};
  const { stdout, stderr, files, output, error, success, executionEnv, ...args } = state;
  return args;
}

function resolveCoords(
  toolName: string,
  state: Record<string, unknown> | undefined,
): { apiName: string; identifier: string } | undefined {
  const pair = WIRE[toolName];
  if (!pair) return undefined;
  const [identifier, apiName] = pair;
  if (toolName === 'import_skill' && state && typeof state.identifier === 'string' && state.identifier) {
    return { identifier, apiName: 'importFromMarket' };
  }
  return { identifier, apiName };
}

async function* readSse(response: Response): AsyncGenerator<JournalFrame> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('live: empty body');
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    while (true) {
      const idx = buf.indexOf('\n\n');
      if (idx < 0) break;
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let eventName = '';
      let dataLine = '';
      let id = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) eventName = line.slice(7).trim();
        if (line.startsWith('data: ')) dataLine = line.slice(6);
        if (line.startsWith('id: ')) id = line.slice(4).trim();
      }
      if (!eventName || !dataLine) continue;
      try {
        const data = JSON.parse(dataLine) as Record<string, unknown>;
        const inner =
          data.event && typeof data.event === 'object'
            ? (data.event as Record<string, unknown>)
            : data;
        yield {
          event: eventName,
          id,
          seq: typeof data.seq === 'number' ? data.seq : undefined,
          event_type: typeof data.event_type === 'string' ? data.event_type : eventName,
          eventPayload: inner,
        };
      } catch {
        /* skip bad frame */
      }
    }
  }
}

type RunSnapshot = {
  approval_request?: { answer?: string; type?: string } & Record<string, unknown>;
  error?: string;
  status?: string;
};

const TERMINAL = new Set(['canceled', 'completed', 'failed']);

async function fetchRun(runId: string): Promise<RunSnapshot> {
  const res = await fetch(`/lca-api/runs/${runId}`, {
    headers: { Authorization: `Bearer ${LCA_TOKEN}` },
  });
  if (!res.ok) return {};
  return (await res.json()) as RunSnapshot;
}

async function postAnswer(runId: string, answer: string, signal: AbortSignal): Promise<void> {
  await fetch(`/lca-api/runs/${runId}/answer`, {
    body: JSON.stringify({ answer }),
    headers: {
      Authorization: `Bearer ${LCA_TOKEN}`,
      'Content-Type': 'application/json',
    },
    method: 'POST',
    signal,
  });
}

async function waitWhileWaiting(
  runId: string,
  signal: AbortSignal,
): Promise<RunSnapshot> {
  while (!signal.aborted) {
    const snap = await fetchRun(runId);
    const pending = snap.approval_request?.answer;
    if (typeof pending === 'string' && pending.trim()) {
      await postAnswer(runId, pending.trim(), signal).catch(() => undefined);
    }
    if (snap.status !== 'waiting_input') return snap;
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  return { status: 'canceled' };
}

class AlwaysRetryOnce implements LLMRetryPolicy {
  classifyError(error: unknown): ClassifiedLLMError {
    const message = error instanceof Error ? error.message : String(error);
    return { kind: 'stop', message };
  }

  maxAttempts(_provider: string): number {
    return 1;
  }

  resolveRetryBudget(_provider: string, _error: unknown): number {
    return 0;
  }
}

interface Options {
  get: () => ChatStore;
  operationId: string;
  session: ClientRuntimeSession;
  toggleToolCallingStreaming: (id: string, streaming: boolean[] | undefined) => void;
}

function toolCallId(payload: Record<string, unknown>, fallback: string): string {
  const invocation = payload.invocation_id;
  if (typeof invocation === 'string' && invocation) return invocation;
  return fallback;
}

export class JournalTransport implements LLMTransport {
  readonly retryPolicy: LLMRetryPolicy = new AlwaysRetryOnce();

  constructor(private readonly context: Options) {}

  async runAttempt(input: LLMAttemptInput): Promise<LLMAttemptExecution> {
    const operation = this.context.get().operations[this.context.operationId];
    if (!operation) throw new Error(`Operation not found: ${this.context.operationId}`);
    const assistantMessageId = this.context.session.assistantMessageId;
    if (!assistantMessageId) throw new Error('journal: missing assistant message id');

    const messages = input.context.messages ?? [];
    const offeredToolNames = (input.context.resolvedTools?.tools ?? []).map(
      (tool) => tool.function.name,
    );

    const makeHandler = () =>
      new StreamingHandler(
        {
          agentId: operation.context.agentId ?? '',
          groupId: operation.context.groupId,
          messageId: assistantMessageId,
          operationId: this.context.operationId,
          topicId: operation.context.topicId,
        },
        {
          onContentUpdate: (content, reasoning) =>
            this.dispatchMessage(assistantMessageId, { content, reasoning }),
          onGroundingUpdate: (search) => this.dispatchMessage(assistantMessageId, { search }),
          onImagesUpdate: (imageList) => this.dispatchMessage(assistantMessageId, { imageList }),
          onReasoningComplete: (operationId) => this.context.get().completeOperation(operationId),
          onReasoningStart: () => {
            const { operationId } = this.context.get().startOperation({
              context: {
                ...operation.context,
                agentId: operation.context.agentId,
                messageId: assistantMessageId,
              },
              parentOperationId: this.context.operationId,
              type: 'reasoning',
            });
            this.context.get().associateMessageWithOperation(assistantMessageId, operationId);
            return operationId;
          },
          onReasoningUpdate: (reasoning) =>
            this.dispatchMessage(assistantMessageId, { reasoning }),
          onToolCallsUpdate: (tools) => this.dispatchMessage(assistantMessageId, { tools }),
          toggleToolCallingStreaming: this.context.toggleToolCallingStreaming,
          transformToolCalls: (calls) =>
            this.context.get().internal_transformToolCalls(calls, offeredToolNames),
          uploadBase64Image: async () => ({}),
        },
      );

    let handler = makeHandler();
    let turnHadTool = false;
    let lastSeq = 0;
    let runId = '';
    let runError: string | undefined;
    let finished = false;

    const dispatch = (frame: JournalFrame): 'mapped' | 'skip' => {
      const payload = frame.eventPayload ?? {};
      switch (frame.event) {
        case 'ReasoningDelta': {
          if (turnHadTool) {
            void handler.handleFinish({ type: 'stop' });
            handler = makeHandler();
            turnHadTool = false;
          }
          handler.handleChunk({
            text: String(payload.text_delta ?? ''),
            type: 'reasoning',
          });
          return 'mapped';
        }
        case 'ReasoningCompleted':
          return 'skip';
        case 'StepTextDelta': {
          if (payload.channel && payload.channel !== 'answer') return 'skip';
          handler.handleChunk({ text: String(payload.text_delta ?? ''), type: 'text' });
          return 'mapped';
        }
        case 'ToolStarted': {
          const toolName = String(payload.tool_name ?? '');
          const state = (payload.plugin_state as Record<string, unknown> | undefined) ?? {};
          const coords = resolveCoords(toolName, state);
          if (!coords) return 'skip';
          turnHadTool = true;
          const id = toolCallId(payload, `call_${frame.seq ?? lastSeq}`);
          const toolCalls: MessageToolCall[] = [
            {
              function: {
                arguments: JSON.stringify(pickArgs(state)),
                name: `${coords.identifier}____${coords.apiName}`,
              },
              id,
              type: 'function',
            },
          ];
          handler.handleChunk({
            isAnimationActives: [true],
            tool_calls: toolCalls,
            type: 'tool_calls',
          });
          return 'mapped';
        }
        case 'SandboxOutputDelta': {
          const tools = handler.getTools() ?? [];
          const id = toolCallId(payload, '');
          const target = tools.find((tool) => tool.id === id) ?? tools.at(-1);
          if (!target) return 'skip';
          const stream = String(payload.stream ?? 'stdout');
          const delta = String(payload.text_delta ?? '');
          const prev =
            target.result && typeof target.result === 'object'
              ? ((target.result as { state?: Record<string, unknown> }).state ?? {})
              : {};
          const nextState = { ...prev, [stream]: `${String(prev[stream] ?? '')}${delta}` };
          target.result = { ...(target.result as object), id: target.id, state: nextState };
          this.context.get().internal_dispatchMessage(
            { id: assistantMessageId, type: 'updateMessage', value: { tools: [...tools] } },
            { operationId: this.context.operationId },
          );
          return 'mapped';
        }
        case 'ToolInvoked': {
          turnHadTool = true;
          const tools = handler.getTools() ?? [];
          const id = toolCallId(payload, '');
          const target = tools.find((tool) => tool.id === id) ?? tools.at(-1);
          if (!target) return 'skip';
          const state = (payload.plugin_state as Record<string, unknown> | undefined) ?? {};
          target.result = {
            content: String(payload.result_preview ?? ''),
            error: payload.ok === false ? String(payload.error ?? '') : undefined,
            id: target.id,
            state,
          };
          this.context.toggleToolCallingStreaming(
            assistantMessageId,
            tools.map(() => false),
          );
          this.context.get().internal_dispatchMessage(
            { id: assistantMessageId, type: 'updateMessage', value: { tools: [...tools] } },
            { operationId: this.context.operationId },
          );
          return 'mapped';
        }
        case 'ToolDenied': {
          const tools = handler.getTools() ?? [];
          const target = tools.at(-1);
          if (!target) return 'skip';
          target.result = {
            error: String(payload.reason ?? payload.error ?? 'denied'),
            id: target.id,
            state: {},
          };
          this.context.get().internal_dispatchMessage(
            { id: assistantMessageId, type: 'updateMessage', value: { tools: [...tools] } },
            { operationId: this.context.operationId },
          );
          return 'mapped';
        }
        case 'AgentRunFinished':
        case 'TeamRunFinished': {
          finished = true;
          if (payload.error) runError = String(payload.error);
          handler.handleChunk({ type: 'stop' });
          return 'mapped';
        }
        case 'LiveGap':
          hopLog('H4', runId, { event: 'LiveGap', mapped: 'skip' });
          return 'skip';
        default:
          return 'skip';
      }
    };

    try {
      const createRes = await fetch('/lca-api/runs', {
        body: JSON.stringify({ messages, model: input.model }),
        headers: {
          Authorization: `Bearer ${LCA_TOKEN}`,
          'Content-Type': 'application/json',
        },
        method: 'POST',
        signal: operation.abortController.signal,
      });
      if (!createRes.ok) {
        const text = await createRes.text();
        throw new Error(`create run HTTP ${createRes.status}: ${text.slice(0, 200)}`);
      }
      const created = (await createRes.json()) as { run_id: string; trace_id: string };
      runId = created.run_id;
      this.dispatchMessage(assistantMessageId, {
        metadata: { lca: { hop: 'H1', run_id: created.run_id, trace_id: created.trace_id } },
      });

      input.onFirstChunk?.();
      const firstFrame = Date.now();
      let sawFrame = false;
      let afterSeq = 0;
      const signal = operation.abortController.signal;

      const onFrame = (frame: JournalFrame): void => {
        if (typeof frame.seq === 'number') lastSeq = frame.seq;
        const mapped = dispatch(frame);
        if (!sawFrame) {
          sawFrame = true;
          hopLog('H4', runId, { event: frame.event, mapped, seq: frame.seq });
        } else if (mapped === 'mapped' || MUST_MAP.has(frame.event)) {
          hopLog('H5', runId, { event: frame.event, mapped, seq: frame.seq });
        }
      };

      while (!finished && !signal.aborted) {
        const streamRes = await fetch(`/lca-api/runs/${runId}/live`, {
          headers: {
            Authorization: `Bearer ${LCA_TOKEN}`,
            'Last-Event-ID': String(afterSeq),
          },
          signal,
        });
        if (!streamRes.ok) {
          const text = await streamRes.text();
          throw new Error(`live HTTP ${streamRes.status}: ${text.slice(0, 200)}`);
        }
        for await (const frame of readSse(streamRes)) {
          onFrame(frame);
          if (typeof frame.seq === 'number') afterSeq = frame.seq;
          if (finished) break;
        }
        if (Date.now() - firstFrame > FIRST_FRAME_MS && !sawFrame) {
          hopLog('H4', runId, { summary: 'no SSE frame' });
        }
        if (finished || signal.aborted) break;
        const snap = await fetchRun(runId);
        if (snap.status === 'waiting_input') {
          hopLog('H5', runId, { status: 'waiting_input' });
          this.dispatchMessage(assistantMessageId, {
            metadata: {
              lca: {
                approval_request: snap.approval_request,
                run_id: runId,
                status: 'waiting_input',
              },
            },
          });
          const next = await waitWhileWaiting(runId, signal);
          if (next.status === 'waiting_input' || signal.aborted) break;
          continue;
        }
        if (TERMINAL.has(String(snap.status ?? ''))) break;
        hopLog('H4', runId, { after_seq: afterSeq, summary: 'live reconnect' });
      }
      if (!sawFrame) hopLog('H4', runId, { summary: 'no SSE frame' });
    } catch (error) {
      if (operation.abortController.signal.aborted) {
        await fetch(`/lca-api/runs/${runId}/cancel`, { method: 'POST' }).catch(() => undefined);
        const result = await handler.handleFinish({ type: 'abort' });
        return { ok: true, output: this.toOutput(handler, result, 'abort') };
      }
      return {
        error: error instanceof Error ? error : new Error(String(error)),
        ok: false,
        output: this.toOutput(handler, await handler.handleFinish({ type: 'error' }), 'error'),
      };
    }

    const result = await handler.handleFinish({ type: runError ? 'error' : 'stop' });
    const output = this.toOutput(handler, result, runError ? 'error' : 'stop');
    if (runError) {
      return { error: new Error(runError), ok: false, output };
    }
    return { ok: true, output };
  }

  async stream(
    _payload: LLMStreamPayload,
    _handlers?: Parameters<LLMTransport['stream']>[1],
    _signal?: AbortSignal,
  ): Promise<LLMStreamResult> {
    throw new Error('JournalTransport.stream is not used; use runAttempt');
  }

  private dispatchMessage(id: string, value: Record<string, unknown>): void {
    this.context.get().internal_dispatchMessage(
      { id, type: 'updateMessage', value },
      { operationId: this.context.operationId },
    );
  }

  private toOutput(
    handler: StreamingHandler,
    result: Awaited<ReturnType<StreamingHandler['handleFinish']>>,
    finish: string,
  ): LLMAttemptOutput {
    return {
      answerSalvagedFromReasoning: false,
      content: handler.getOutput(),
      contentParts: [],
      finishReason: finish,
      grounding: null,
      hasContentImages: false,
      hasReasoningImages: false,
      imageList: [],
      lcaClosedLoop: true,
      reasoning: result.metadata.reasoning,
      reasoningParts: [],
      thinkingContent: handler.getThinkingContent(),
      toolCalls: [],
      toolsCalling: handler.getTools() ?? [],
    };
  }
}
"""


def apply(ctx: PatchContext) -> bool:
    rel = "src/store/chat/agents/transports/JournalTransport.ts"
    changed = ctx.write_if_changed(rel, _transport_ts())

    host = "src/store/chat/agents/transports/buildClientRuntimeHost.ts"
    text = ctx.read(host)

    if "JournalTransport" not in text:
        text = text.replace(
            "import { ClientLLMTransport } from './ClientLLMTransport';\n",
            "import { JournalTransport } from './JournalTransport';\n"
            "import { ClientLLMTransport } from './ClientLLMTransport';\n",
        )
        text = text.replace(
            "import { AgentTimelineTransport } from './AgentTimelineTransport';\n",
            "import { JournalTransport } from './JournalTransport';\n",
        )
        changed = True

    expected = (
        "llm: new JournalTransport({\n"
        "        get: context.get,\n"
        "        operationId: context.operationId,\n"
        "        session,\n"
        "        toggleToolCallingStreaming"
    )
    if expected not in text:
        text = re.sub(
            r"llm: new (?:JournalTransport|AgentTimelineTransport|ClientLLMTransport)\(\{\n"
            r"        get: context\.get,\n"
            r"(?:        metadata: context\.metadata,\n)?"
            r"        operationId: context\.operationId,\n"
            r"        session,\n"
            r"(?:        toggleToolCallingStreaming[^}]*\n)?"
            r"      \}\),\n",
            "llm: new JournalTransport({\n"
            "        get: context.get,\n"
            "        operationId: context.operationId,\n"
            "        session,\n"
            "        toggleToolCallingStreaming: (id, streaming) =>\n"
            "          context.get().internal_toggleToolCallingStreaming(id, streaming),\n"
            "      }),\n",
            text,
        )
        changed = True

    if changed:
        ctx.write(host, text)
    return changed
