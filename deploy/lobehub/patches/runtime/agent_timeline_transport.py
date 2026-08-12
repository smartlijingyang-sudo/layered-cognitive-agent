"""Patch: AgentTimelineTransport — consume timeline.v1 SSE (no OpenAI chunks)."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="agent_timeline_transport",
    description="LCA agent stream via timeline.v1 SSE",
    files=(
        "src/store/chat/agents/transports/AgentTimelineTransport.ts",
        "src/store/chat/agents/transports/buildClientRuntimeHost.ts",
    ),
    risk="high",
    category="runtime",
    depends_on=(),
    why="Agent runs emit timeline.v1 only; OpenAI chunk + lca.events path is removed",
    technical_detail="Add AgentTimelineTransport; wire as llm transport for all client runs",
    verify_file="src/store/chat/agents/transports/AgentTimelineTransport.ts",
    verify_marker="timeline.v1",
)

_TRANSPORT_TS = r'''import type {
  LLMAttemptExecution,
  LLMAttemptInput,
  LLMAttemptOutput,
  LLMRetryPolicy,
  LLMStreamPayload,
  LLMStreamResult,
  LLMTransport,
} from '@lobechat/agent-runtime';
import type { ChatToolPayload, ModelReasoning } from '@lobechat/types';

import type { ChatStore } from '@/store/chat/store';

import type { ClientRuntimeSession } from './ClientRuntimeStreamSink';

/** Gateway base without trailing /v1 */
function gatewayBase(): string {
  const raw =
    (typeof process !== 'undefined' &&
      (process.env.NEXT_PUBLIC_LCA_GATEWAY ||
        process.env.OPENAI_PROXY_URL ||
        process.env.QWEN_PROXY_URL)) ||
    'http://127.0.0.1:8765';
  return String(raw).replace(/\/v1\/?$/, '').replace(/\/$/, '');
}

type TimelineState = {
  answer: string;
  tools: Map<string, ChatToolPayload>;
  thinkingSections: { step: number; content: string }[];
  currentThinking: string;
  currentStep: number;
  status: string;
  error?: string;
};

function emptyState(): TimelineState {
  return {
    answer: '',
    tools: new Map(),
    thinkingSections: [],
    currentThinking: '',
    currentStep: 0,
    status: 'running',
  };
}

function applyEvent(state: TimelineState, type: string, data: Record<string, unknown>): TimelineState {
  switch (type) {
    case 'thinking.delta': {
      const step = Number(data.step ?? state.currentStep);
      const text = String(data.text ?? '');
      return {
        ...state,
        currentStep: step,
        currentThinking: state.currentThinking + text,
      };
    }
    case 'thinking.end': {
      const step = Number(data.step ?? state.currentStep);
      const content = String(data.content ?? state.currentThinking);
      return {
        ...state,
        currentThinking: '',
        thinkingSections: [...state.thinkingSections, { step, content }],
      };
    }
    case 'answer.delta':
      return { ...state, answer: state.answer + String(data.text ?? '') };
    case 'tool.start': {
      const id = String(data.tool_call_id ?? '');
      const wire = String(data.wire_name ?? data.name ?? 'tool');
      const [identifier, apiName] = wire.includes('____')
        ? (wire.split('____') as [string, string])
        : ['lca', wire];
      const tool: ChatToolPayload = {
        id,
        identifier,
        apiName,
        arguments: String(data.arguments ?? '{}'),
        type: 'default',
      };
      const next = new Map(state.tools);
      next.set(id, tool);
      return { ...state, tools: next };
    }
    case 'tool.delta':
    case 'tool.end': {
      const id = String(data.tool_call_id ?? '');
      const existing = state.tools.get(id);
      if (!existing) return state;
      const pluginState = {
        ...(typeof existing.result === 'object' && existing.result && 'state' in existing.result
          ? ((existing.result as { state?: Record<string, unknown> }).state ?? {})
          : {}),
        ...((data.state as Record<string, unknown>) ?? {}),
        ...(type === 'tool.end' && data.files ? { files: data.files } : {}),
      };
      const content =
        type === 'tool.end'
          ? String(data.content ?? '')
          : String(data.text ?? (pluginState.output as string) ?? '');
      const updated: ChatToolPayload = {
        ...existing,
        result: {
          id,
          content,
          error: type === 'tool.end' && data.error ? String(data.error) : undefined,
          state: pluginState,
        },
      };
      const next = new Map(state.tools);
      next.set(id, updated);
      return { ...state, tools: next };
    }
    case 'run.end':
      return {
        ...state,
        status: String(data.status ?? 'completed'),
        error: data.error ? String(data.error) : undefined,
        answer: state.answer || String(data.output ?? ''),
      };
    default:
      return state;
  }
}

async function* readTimelineSse(
  response: Response,
): AsyncGenerator<{ type: string; data: Record<string, unknown> }> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('timeline: empty body');
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
      let etype = '';
      let dataLine = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) etype = line.slice(7).trim();
        if (line.startsWith('data: ')) dataLine = line.slice(6);
      }
      if (!etype || !dataLine) continue;
      try {
        const data = JSON.parse(dataLine) as Record<string, unknown>;
        yield { type: etype, data };
      } catch {
        /* skip bad frame */
      }
    }
  }
}

class AlwaysRetryOnce implements LLMRetryPolicy {
  async shouldRetry(): Promise<boolean> {
    return false;
  }
}

interface Options {
  get: () => ChatStore;
  operationId: string;
  session: ClientRuntimeSession;
}

/**
 * LLM transport for LCA agent runs — timeline.v1 SSE only.
 */
export class AgentTimelineTransport implements LLMTransport {
  readonly retryPolicy: LLMRetryPolicy = new AlwaysRetryOnce();

  constructor(private readonly context: Options) {}

  async runAttempt(input: LLMAttemptInput): Promise<LLMAttemptExecution> {
    const operation = this.context.get().operations[this.context.operationId];
    if (!operation) throw new Error(`Operation not found: ${this.context.operationId}`);
    const assistantMessageId = this.context.session.assistantMessageId;
    if (!assistantMessageId) throw new Error('timeline: missing assistant message id');

    const modelParameters = input.context.modelParameters as
      | { params?: Record<string, unknown>; options?: { signal?: AbortSignal } }
      | undefined;
    const messages = input.context.messages ?? [];
    const base = gatewayBase();
    const url = `${base}/v1/chat/completions`;

    let state = emptyState();
    const dispatch = (partial: Record<string, unknown>) => {
      this.context
        .get()
        .internal_dispatchMessage(
          { id: assistantMessageId, type: 'updateMessage', value: partial },
          { operationId: this.context.operationId },
        );
    };

    const publish = () => {
      const sections = [...state.thinkingSections.map((s) => s.content)];
      if (state.currentThinking) sections.push(state.currentThinking);
      const reasoning: ModelReasoning | undefined = sections.length
        ? {
            content: sections.join('\n\n'),
            isMultimodal: sections.length > 1,
          }
        : undefined;
      dispatch({
        content: state.answer,
        reasoning,
        tools: [...state.tools.values()],
      });
    };

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer lca-local',
        },
        body: JSON.stringify({
          model: input.model,
          stream: true,
          messages,
          ...(modelParameters?.params ?? {}),
        }),
        signal: operation.abortController.signal,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`timeline HTTP ${res.status}: ${text.slice(0, 200)}`);
      }
      input.onFirstChunk?.();

      for await (const { type, data } of readTimelineSse(res)) {
        state = applyEvent(state, type, data);
        publish();
        if (type === 'run.end') break;
      }
    } catch (error) {
      if (operation.abortController.signal.aborted) {
        return { ok: true, output: this.toOutput(state, 'abort') };
      }
      return {
        ok: false,
        error: error instanceof Error ? error : new Error(String(error)),
        output: this.toOutput(state, 'error'),
      };
    }

    if (state.status === 'failed' || state.error) {
      return {
        ok: false,
        error: new Error(state.error || 'run failed'),
        output: this.toOutput(state, 'error'),
      };
    }
    return { ok: true, output: this.toOutput(state, 'stop') };
  }

  async stream(
    _payload: LLMStreamPayload,
    _handlers?: Parameters<LLMTransport['stream']>[1],
    _signal?: AbortSignal,
  ): Promise<LLMStreamResult> {
    throw new Error('AgentTimelineTransport.stream is not used; use runAttempt');
  }

  private toOutput(state: TimelineState, finish: string): LLMAttemptOutput {
    const sections = [...state.thinkingSections.map((s) => s.content)];
    if (state.currentThinking) sections.push(state.currentThinking);
    const thinkingContent = sections.join('\n\n');
    return {
      content: state.answer,
      thinkingContent,
      contentParts: [],
      reasoningParts: sections.map((text) => ({ type: 'text' as const, text })),
      finishReason: finish,
      grounding: null,
      hasContentImages: false,
      hasReasoningImages: false,
      imageList: [],
      toolCalls: [],
      toolsCalling: [...state.tools.values()],
      lcaClosedLoop: true,
      answerSalvagedFromReasoning: false,
    };
  }
}
'''


def apply(ctx: PatchContext) -> bool:
    rel = "src/store/chat/agents/transports/AgentTimelineTransport.ts"
    created = ctx.create_file(rel, _TRANSPORT_TS)
    # If file exists from prior apply, refresh content for pure timeline
    if not created and not ctx.has_marker(rel, "timeline.v1"):
        ctx.write(rel, _TRANSPORT_TS)
        created = True
    elif not created and ctx.has_marker(rel, "timeline.v1"):
        # force rewrite for thoroughness
        ctx.write(rel, _TRANSPORT_TS)

    host = "src/store/chat/agents/transports/buildClientRuntimeHost.ts"
    text = ctx.read(host)
    if "AgentTimelineTransport" not in text:
        text = text.replace(
            "import { ClientLLMTransport } from './ClientLLMTransport';\n",
            "import { AgentTimelineTransport } from './AgentTimelineTransport';\n"
            "import { ClientLLMTransport } from './ClientLLMTransport';\n",
        )
        text = text.replace(
            "      llm: new ClientLLMTransport({\n"
            "        get: context.get,\n"
            "        metadata: context.metadata,\n"
            "        operationId: context.operationId,\n"
            "        session,\n"
            "      }),\n",
            "      // LCA: agent runs use timeline.v1 (not OpenAI chunks)\n"
            "      llm: new AgentTimelineTransport({\n"
            "        get: context.get,\n"
            "        operationId: context.operationId,\n"
            "        session,\n"
            "      }),\n",
        )
        ctx.write(host, text)
        return True
    return created
