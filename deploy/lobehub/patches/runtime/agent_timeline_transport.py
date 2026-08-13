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

_TRANSPORT_TS = r"""import type {
  ClassifiedLLMError,
  LLMAttemptExecution,
  LLMAttemptInput,
  LLMAttemptOutput,
  LLMRetryPolicy,
  LLMStreamPayload,
  LLMStreamResult,
  LLMTransport,
} from '@lobechat/agent-runtime';
import type { ChatToolPayload, MessageContentPart, ModelReasoning } from '@lobechat/types';

import type { ChatStore } from '@/store/chat/store';

import type { ClientRuntimeSession } from './ClientRuntimeStreamSink';

const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';

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
      // 后端 LobeHubSSEAdapter 已经 resolve 了 wire_name → identifier/api_name
      // 直接用，不再重新解析（避免 fallback 到 'lca'）
      const tool: ChatToolPayload = {
        id,
        identifier: String(data.identifier ?? 'lca'),
        apiName: String(data.api_name ?? data.name ?? 'tool'),
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

    const messages = input.context.messages ?? [];

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
      const sectionTexts = [...state.thinkingSections.map((s) => s.content)];
      if (state.currentThinking) sectionTexts.push(state.currentThinking);

      // 多段 reasoning：用 tempDisplayContent 让前端渲染为独立可折叠块
      // 单段或无段：退化为普通 content 字符串
      const reasoning: ModelReasoning | undefined = sectionTexts.length
        ? sectionTexts.length > 1
          ? {
              content: sectionTexts.join('\n\n'),
              isMultimodal: true,
              tempDisplayContent: sectionTexts.map(
                (text): MessageContentPart => ({ text, type: 'text' }),
              ),
            }
          : { content: sectionTexts[0] }
        : undefined;

      dispatch({
        content: state.answer,
        reasoning,
        tools: [...state.tools.values()],
      });
    };

    try {
      const createRes = await fetch(`/lca-api/agent/runs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${LCA_TOKEN}`,
        },
        body: JSON.stringify({ messages, model: input.model }),
        signal: operation.abortController.signal,
      });
      if (!createRes.ok) {
        const text = await createRes.text();
        throw new Error(`create run HTTP ${createRes.status}: ${text.slice(0, 200)}`);
      }
      const { run_id } = (await createRes.json()) as { run_id: string; trace_id: string };

      const streamRes = await fetch(`/lca-api/agent/runs/${run_id}/timeline`, {
        headers: { Authorization: 'Bearer lca-local' },
        signal: operation.abortController.signal,
      });
      if (!streamRes.ok) {
        const text = await streamRes.text();
        throw new Error(`timeline HTTP ${streamRes.status}: ${text.slice(0, 200)}`);
      }
      input.onFirstChunk?.();

      for await (const { type, data } of readTimelineSse(streamRes)) {
        state = applyEvent(state, type, data);

        // 工具调用动画：新工具到达 → 开，run 结束 → 关
        if (type === 'tool.start') {
          this.context.toggleToolCallingStreaming(assistantMessageId, [true]);
        }

        publish();
        if (type === 'run.end') {
          this.context.toggleToolCallingStreaming(assistantMessageId, undefined);
          break;
        }
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
    const sectionTexts = [...state.thinkingSections.map((s) => s.content)];
    if (state.currentThinking) sectionTexts.push(state.currentThinking);
    const thinkingContent = sectionTexts.join('\n\n');

    // 持久化 reasoning — 多段用 tempDisplayContent，单段用 content
    const reasoning: ModelReasoning | undefined = sectionTexts.length
      ? sectionTexts.length > 1
        ? {
            content: thinkingContent,
            isMultimodal: true,
            tempDisplayContent: sectionTexts.map(
              (text): MessageContentPart => ({ text, type: 'text' }),
            ),
          }
        : { content: thinkingContent }
      : undefined;

    return {
      content: state.answer,
      thinkingContent,
      contentParts: [],
      reasoningParts: sectionTexts.map((text) => ({ type: 'text' as const, text })),
      reasoning,
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
"""


def apply(ctx: PatchContext) -> bool:
    rel = "src/store/chat/agents/transports/AgentTimelineTransport.ts"
    changed = ctx.write_if_changed(rel, _TRANSPORT_TS)

    host = "src/store/chat/agents/transports/buildClientRuntimeHost.ts"
    text = ctx.read(host)

    # 确保 import 存在（首次 patch 或 reset 后）
    if "AgentTimelineTransport" not in text:
        text = text.replace(
            "import { ClientLLMTransport } from './ClientLLMTransport';\n",
            "import { AgentTimelineTransport } from './AgentTimelineTransport';\n"
            "import { ClientLLMTransport } from './ClientLLMTransport';\n",
        )
        changed = True

    # 确保 llm transport 实例化包含 toggleToolCallingStreaming
    # 匹配两种状态：原版（ClientLLMTransport）或已 patch 但缺新字段
    expected_host_snippet = (
        "llm: new AgentTimelineTransport({\n"
        "        get: context.get,\n"
        "        operationId: context.operationId,\n"
        "        session,\n"
        "        toggleToolCallingStreaming"
    )
    if expected_host_snippet not in text:
        # 还原锚点：匹配原版或已 patch 但不完整的版本
        import re

        text = re.sub(
            r"llm: new (?:Agent|Client)LLMTransport\(\{\n"
            r"        get: context\.get,\n"
            r"(?:        metadata: context\.metadata,\n)?"
            r"        operationId: context\.operationId,\n"
            r"        session,\n"
            r"(?:        toggleToolCallingStreaming[^}]*\n)?"
            r"      \}\),\n",
            "llm: new AgentTimelineTransport({\n"
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
