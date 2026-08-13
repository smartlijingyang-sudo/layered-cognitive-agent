"""Patch: LcaRunDriver — project one Journal Run onto native LobeHub UI.

LCA owns the agent loop. The browser posts once, subscribes to /live,
and opens a new assistant bubble + StreamingHandler on each LlmCallStarted.
It does not run GeneralChatAgent or invoke tools.
"""

from __future__ import annotations

from collections.abc import Mapping

from deploy.lobehub.engine import PatchContext, PatchMeta
from gateway.runs.wire import WIRE

meta = PatchMeta(
    name="lca_run_driver",
    description="Project Journal SSE; LCA owns the loop",
    files=(
        "src/store/chat/agents/transports/LcaRunDriver.ts",
        "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts",
    ),
    risk="high",
    category="runtime",
    depends_on=(),
    why="LobeHub AgentRuntime owns a client tool loop; LCA already ran the loop on the server",
    technical_detail=(
        "executeClientAgent short-circuits for solo/team/auto into runLcaJournal. "
        "Each LlmCallStarted opens a new assistant message and StreamingHandler."
    ),
    verify_file="src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts",
    verify_marker="runLcaJournal",
)


def render_wire_ts(wire: Mapping[str, tuple[str, str]]) -> str:
    lines = ["const WIRE: Record<string, readonly [string, string]> = {"]
    for name, (identifier, api_name) in wire.items():
        lines.append(f"  '{name}': ['{identifier}', '{api_name}'],")
    lines.append("};")
    return "\n".join(lines)


def _driver_ts() -> str:
    return _DRIVER_TEMPLATE.replace("/* __WIRE__ */", render_wire_ts(WIRE))


_DRIVER_TEMPLATE = r"""import type { ChatToolPayload, MessageToolCall, UIChatMessage } from '@lobechat/types';

import type { ChatStore } from '@/store/chat/store';

import { StreamingHandler } from '../StreamingHandler';

const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';

/* __WIRE__ */

type JournalFrame = {
  event: string;
  seq?: number;
  eventPayload?: Record<string, unknown>;
};

type Projected =
  | { kind: 'ignore' }
  | { kind: 'open-turn' }
  | { kind: 'reasoning'; text: string }
  | { kind: 'text'; text: string }
  | { kind: 'tool-start'; toolName: string; state: Record<string, unknown>; idHint: string }
  | { kind: 'sandbox-delta'; stream: string; text: string; payload: Record<string, unknown> }
  | { kind: 'tool-invoked'; payload: Record<string, unknown>; state: Record<string, unknown> }
  | { kind: 'tool-denied'; payload: Record<string, unknown>; reason: string }
  | { kind: 'run-finished'; error?: string }
  | { kind: 'live-gap' };

const TERMINAL = new Set(['canceled', 'completed', 'failed']);

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

function toolCallId(payload: Record<string, unknown>, fallback: string): string {
  const invocation = payload.invocation_id;
  if (typeof invocation === 'string' && invocation) return invocation;
  return fallback;
}

function findTurnTool<T extends { call: MessageToolCall }>(
  turnTools: T[],
  payload: Record<string, unknown>,
): T | undefined {
  const id = toolCallId(payload, '');
  const matched = turnTools.find((item) => item.call.id === id);
  if (matched) return matched;
  if (id) return undefined;
  return turnTools.at(-1);
}

function toWireMessages(messages: UIChatMessage[]): { content: string; role: string }[] {
  return messages
    .filter((message) => message.role === 'user' || message.role === 'assistant' || message.role === 'system')
    .map((message) => ({
      content: typeof message.content === 'string' ? message.content : '',
      role: message.role,
    }));
}

function parseSseBlock(block: string): JournalFrame | null {
  let eventName = '';
  let idLine = '';
  const dataLines: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('id:') || line.startsWith('id: ')) idLine = line.replace(/^id:\s?/, '').trim();
    else if (line.startsWith('event:') || line.startsWith('event: '))
      eventName = line.replace(/^event:\s?/, '').trim();
    else if (line.startsWith('data:') || line.startsWith('data: '))
      dataLines.push(line.replace(/^data:\s?/, ''));
  }
  if (!eventName || !dataLines.length) return null;
  try {
    const data = JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
    const inner =
      data.event && typeof data.event === 'object'
        ? (data.event as Record<string, unknown>)
        : data;
    const seqFromId = Number(idLine);
    return {
      event: eventName,
      seq: typeof data.seq === 'number' ? data.seq : Number.isFinite(seqFromId) ? seqFromId : undefined,
      eventPayload: inner,
    };
  } catch {
    return null;
  }
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
      const frame = parseSseBlock(block);
      if (frame) yield frame;
    }
  }
}

function projectJournalFrame(frame: JournalFrame): Projected {
  const payload = frame.eventPayload ?? {};
  switch (frame.event) {
    case 'LlmCallStarted':
      return { kind: 'open-turn' };
    case 'ReasoningDelta':
      return { kind: 'reasoning', text: String(payload.text_delta ?? '') };
    case 'StepTextDelta':
      if (payload.channel && payload.channel !== 'answer') return { kind: 'ignore' };
      return { kind: 'text', text: String(payload.text_delta ?? '') };
    case 'ToolStarted':
      return {
        idHint: toolCallId(payload, `call_${frame.seq ?? 0}`),
        kind: 'tool-start',
        state: (payload.plugin_state as Record<string, unknown> | undefined) ?? {},
        toolName: String(payload.tool_name ?? ''),
      };
    case 'SandboxOutputDelta':
      return {
        kind: 'sandbox-delta',
        payload,
        stream: String(payload.stream ?? 'stdout'),
        text: String(payload.text_delta ?? ''),
      };
    case 'ToolInvoked':
      return {
        kind: 'tool-invoked',
        payload,
        state: (payload.plugin_state as Record<string, unknown> | undefined) ?? {},
      };
    case 'ToolDenied':
      return {
        kind: 'tool-denied',
        payload,
        reason: String(payload.reason ?? payload.error ?? 'denied'),
      };
    case 'AgentRunFinished':
    case 'TeamRunFinished':
      return {
        error: payload.error ? String(payload.error) : undefined,
        kind: 'run-finished',
      };
    case 'LiveGap':
      return { kind: 'live-gap' };
    default:
      return { kind: 'ignore' };
  }
}

export type LcaRunOptions = {
  messages: UIChatMessage[];
  model: string;
  operationId: string;
  parentMessageId: string;
  reuseAssistantId?: string;
  userMessageId?: string;
};

export async function runLcaJournal(get: () => ChatStore, options: LcaRunOptions): Promise<void> {
  const operation = get().operations[options.operationId];
  if (!operation) throw new Error(`Operation not found: ${options.operationId}`);
  const signal = operation.abortController.signal;
  const ctx = operation.context;

  let afterSeq = 0;
  let lastSeq = 0;
  let runId = '';
  let assistantId = '';
  let firstReuse = options.reuseAssistantId;
  let handler: StreamingHandler | null = null;
  let sawContent = false;
  const turnTools: { call: MessageToolCall; result?: ChatToolPayload['result'] }[] = [];

  const dispatchMessage = (id: string, value: Record<string, unknown>) => {
    get().internal_dispatchMessage(
      { id, type: 'updateMessage', value },
      { operationId: options.operationId },
    );
  };

  const resolveTurnTools = (): ChatToolPayload[] => {
    if (!turnTools.length) return [];
    const payloads = get().internal_transformToolCalls(
      turnTools.map((item) => item.call),
    );
    for (const payload of payloads) {
      const rec = turnTools.find((item) => item.call.id === payload.id);
      if (rec?.result) (payload as { result?: typeof rec.result }).result = rec.result;
    }
    return payloads;
  };

  const publishTurnTools = (streaming: boolean) => {
    if (!assistantId) return;
    const payloads = resolveTurnTools();
    if (!payloads.length) return;
    get().internal_toggleToolCallingStreaming(
      assistantId,
      payloads.map(() => streaming),
    );
    dispatchMessage(assistantId, { tools: payloads });
  };

  const makeHandler = (messageId: string) =>
    new StreamingHandler(
      {
        agentId: ctx.agentId ?? '',
        groupId: ctx.groupId,
        messageId,
        operationId: options.operationId,
        topicId: ctx.topicId,
      },
      {
        onContentUpdate: (content, reasoning) => dispatchMessage(messageId, { content, reasoning }),
        onGroundingUpdate: (search) => dispatchMessage(messageId, { search }),
        onImagesUpdate: (imageList) => dispatchMessage(messageId, { imageList }),
        onReasoningComplete: (operationId) => get().completeOperation(operationId),
        onReasoningStart: () => {
          const { operationId } = get().startOperation({
            context: {
              ...ctx,
              agentId: ctx.agentId,
              messageId,
            },
            parentOperationId: options.operationId,
            type: 'reasoning',
          });
          get().associateMessageWithOperation(messageId, operationId);
          return operationId;
        },
        onReasoningUpdate: (reasoning) => dispatchMessage(messageId, { reasoning }),
        onToolCallsUpdate: (tools) => dispatchMessage(messageId, { tools }),
        toggleToolCallingStreaming: (id, streaming) =>
          get().internal_toggleToolCallingStreaming(id, streaming),
        transformToolCalls: (calls) => get().internal_transformToolCalls(calls),
        uploadBase64Image: async () => ({}),
      },
    );

  const finishTurn = async () => {
    if (!handler) return;
    await handler.handleFinish({
      toolCalls: turnTools.map((item) => item.call),
      type: 'stop',
    });
    handler = null;
  };

  const openTurn = async () => {
    await finishTurn();
    sawContent = false;
    turnTools.length = 0;
    let id = firstReuse;
    firstReuse = undefined;
    if (!id) {
      const created = await get().optimisticCreateMessage(
        {
          content: '',
          model: options.model,
          parentId: options.userMessageId ?? options.parentMessageId,
          provider: 'openai',
          role: 'assistant',
          topicId: ctx.topicId,
          ...(ctx.agentId ? { agentId: ctx.agentId } : {}),
          ...(ctx.threadId ? { threadId: ctx.threadId } : {}),
        },
        { operationId: options.operationId },
      );
      id = created?.id;
    }
    if (!id) throw new Error('lca: failed to open assistant turn');
    assistantId = id;
    get().associateMessageWithOperation(id, options.operationId);
    handler = makeHandler(id);
  };

  const ensureTurn = async () => {
    if (!handler) await openTurn();
  };

  const applyProjected = async (projected: Projected): Promise<void> => {
    switch (projected.kind) {
      case 'open-turn': {
        if (handler && (sawContent || turnTools.length > 0)) await openTurn();
        else if (!handler) await openTurn();
        return;
      }
      case 'reasoning': {
        await ensureTurn();
        sawContent = true;
        handler?.handleChunk({ text: projected.text, type: 'reasoning' });
        return;
      }
      case 'text': {
        await ensureTurn();
        sawContent = true;
        handler?.handleChunk({ text: projected.text, type: 'text' });
        return;
      }
      case 'tool-start': {
        await ensureTurn();
        const coords = resolveCoords(projected.toolName, projected.state);
        if (!coords) {
          console.warn('lca: unknown tool', projected.toolName);
          return;
        }
        turnTools.push({
          call: {
            function: {
              arguments: JSON.stringify(pickArgs(projected.state)),
              name: `${coords.identifier}____${coords.apiName}`,
            },
            id: projected.idHint,
            type: 'function',
          },
        });
        handler?.handleChunk({
          isAnimationActives: turnTools.map((item) => !item.result),
          tool_calls: turnTools.map((item) => item.call),
          type: 'tool_calls',
        });
        return;
      }
      case 'sandbox-delta': {
        const rec = findTurnTool(turnTools, projected.payload);
        if (!rec) return;
        const prev = (rec.result?.state as Record<string, unknown> | undefined) ?? {};
        rec.result = {
          ...rec.result,
          content: rec.result?.content ?? '',
          id: rec.call.id,
          state: { ...prev, [projected.stream]: `${String(prev[projected.stream] ?? '')}${projected.text}` },
        };
        publishTurnTools(true);
        return;
      }
      case 'tool-invoked': {
        const rec = findTurnTool(turnTools, projected.payload);
        if (!rec) return;
        rec.result = {
          content: String(projected.payload.result_preview ?? ''),
          error: projected.payload.ok === false ? String(projected.payload.error ?? '') : undefined,
          id: rec.call.id,
          state: projected.state,
        };
        publishTurnTools(false);
        return;
      }
      case 'tool-denied': {
        const rec = findTurnTool(turnTools, projected.payload);
        if (!rec) return;
        rec.result = {
          content: '',
          error: projected.reason,
          id: rec.call.id,
          state: {},
        };
        publishTurnTools(false);
        return;
      }
      case 'run-finished': {
        if (projected.error && assistantId) {
          dispatchMessage(assistantId, {
            error: { message: projected.error, type: 'AgentExecutionError' },
          });
        }
        return;
      }
      case 'live-gap': {
        console.warn('lca: live gap', { afterSeq, lastSeq });
        return;
      }
      default:
        return;
    }
  };

  const createRes = await fetch('/lca-api/runs', {
    body: JSON.stringify({
      messages: toWireMessages(options.messages),
      model: options.model,
    }),
    headers: {
      Authorization: `Bearer ${LCA_TOKEN}`,
      'Content-Type': 'application/json',
    },
    method: 'POST',
    signal,
  });
  if (!createRes.ok) {
    const text = await createRes.text();
    throw new Error(`create run HTTP ${createRes.status}: ${text.slice(0, 200)}`);
  }
  const created = (await createRes.json()) as { run_id: string; trace_id: string };
  runId = created.run_id;
  get().updateOperationMetadata(options.operationId, {
    lca: { run_id: created.run_id, trace_id: created.trace_id },
  });

  const authHeaders = { Authorization: `Bearer ${LCA_TOKEN}` };

  try {
    while (!signal.aborted) {
      const streamRes = await fetch(`/lca-api/runs/${runId}/live`, {
        headers: {
          ...authHeaders,
          'Last-Event-ID': String(afterSeq),
        },
        signal,
      });
      if (!streamRes.ok) {
        const text = await streamRes.text();
        throw new Error(`live HTTP ${streamRes.status}: ${text.slice(0, 200)}`);
      }
      for await (const frame of readSse(streamRes)) {
        if (typeof frame.seq === 'number') {
          lastSeq = frame.seq;
          afterSeq = frame.seq;
        }
        await applyProjected(projectJournalFrame(frame));
      }
      if (signal.aborted) break;
      const snapRes = await fetch(`/lca-api/runs/${runId}`, {
        headers: authHeaders,
      });
      const snap = snapRes.ok ? ((await snapRes.json()) as { status?: string }) : {};
      if (snap.status === 'waiting_input' && assistantId) {
        dispatchMessage(assistantId, {
          metadata: { lca: { run_id: runId, status: 'waiting_input' } },
        });
      }
      if (TERMINAL.has(String(snap.status ?? ''))) break;
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
  } catch (error) {
    if (signal.aborted) {
      await fetch(`/lca-api/runs/${runId}/cancel`, {
        headers: authHeaders,
        method: 'POST',
      }).catch(() => undefined);
      await finishTurn();
      return;
    }
    await finishTurn();
    throw error;
  }
  await finishTurn();
}
"""

_STALE = (
    "src/store/chat/agents/transports/JournalTransport.ts",
    "src/store/chat/agents/transports/LcaResolvedToolTransport.ts",
    "src/store/chat/agents/transports/AgentTimelineTransport.ts",
)

_IMPORT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        "import { createClientRuntimeExecutors } from "
        "'@/store/chat/agents/transports/createClientRuntimeExecutors';\n",
        "import { createClientRuntimeExecutors } from "
        "'@/store/chat/agents/transports/createClientRuntimeExecutors';\n"
        "import { runLcaJournal } from '@/store/chat/agents/transports/LcaRunDriver';\n",
    ),
    (
        "import { createClientRuntimeExecutors } from "
        '"@/store/chat/agents/transports/createClientRuntimeExecutors";\n',
        "import { createClientRuntimeExecutors } from "
        '"@/store/chat/agents/transports/createClientRuntimeExecutors";\n'
        "import { runLcaJournal } from '@/store/chat/agents/transports/LcaRunDriver';\n",
    ),
)

_MODEL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        """    const { agentConfig: agentConfigData } = agentConfig;
    const model = agentConfigData.model;
    const provider = agentConfigData.provider;
""",
        """    const { agentConfig: agentConfigData } = agentConfig;
    const model = agentConfigData.model;
    const provider = agentConfigData.provider;

    /* LCA: runLcaJournal owns solo/team/auto */
    if (model === 'solo' || model === 'team' || model === 'auto') {
      await runLcaJournal(this.#get, {
        messages,
        model,
        operationId,
        parentMessageId,
        reuseAssistantId: params.skipCreateFirstMessage ? params.parentMessageId : undefined,
        userMessageId: params.userMessageId,
      });
      await this.#get().refreshMessages(context);
      const runScope: RunScope = scope === 'sub_agent' ? 'sub_agent' : 'top_level';
      const runLifecycle = buildRunLifecycle(this.#get, {
        context,
        parentMessageId,
        parentMessageType,
        runId: operationId,
        runScope,
        runtimeType: 'client',
      });
      const lifecycleEventBase = {
        context,
        operationId,
        runId: operationId,
        runScope,
        runtimeType: 'client' as const,
      };
      const cancelled = this.#get().operations[operationId]?.status === 'cancelled';
      const completeEvent = {
        ...lifecycleEventBase,
        runtimeStatus: cancelled ? 'interrupted' : 'done',
      };
      const { requeued } = await runLifecycle.completeRun(completeEvent);
      if (!requeued) await runLifecycle.afterRunComplete(completeEvent);
      return { model, provider: provider ?? undefined };
    }
""",
    ),
    (
        """    const { agentConfig: agentConfigData } = agentConfig
    const model = agentConfigData.model
    const provider = agentConfigData.provider
""",
        """    const { agentConfig: agentConfigData } = agentConfig
    const model = agentConfigData.model
    const provider = agentConfigData.provider

    /* LCA: runLcaJournal owns solo/team/auto */
    if (model === 'solo' || model === 'team' || model === 'auto') {
      await runLcaJournal(this.#get, {
        messages,
        model,
        operationId,
        parentMessageId,
        reuseAssistantId: params.skipCreateFirstMessage ? params.parentMessageId : undefined,
        userMessageId: params.userMessageId,
      });
      await this.#get().refreshMessages(context);
      const runScope: RunScope = scope === 'sub_agent' ? 'sub_agent' : 'top_level';
      const runLifecycle = buildRunLifecycle(this.#get, {
        context,
        parentMessageId,
        parentMessageType,
        runId: operationId,
        runScope,
        runtimeType: 'client',
      });
      const lifecycleEventBase = {
        context,
        operationId,
        runId: operationId,
        runScope,
        runtimeType: 'client' as const,
      };
      const cancelled = this.#get().operations[operationId]?.status === 'cancelled';
      const completeEvent = {
        ...lifecycleEventBase,
        runtimeStatus: cancelled ? 'interrupted' : 'done',
      };
      const { requeued } = await runLifecycle.completeRun(completeEvent);
      if (!requeued) await runLifecycle.afterRunComplete(completeEvent);
      return { model, provider: provider ?? undefined };
    }
""",
    ),
)


def apply(ctx: PatchContext) -> bool:
    changed = ctx.write_if_changed(
        "src/store/chat/agents/transports/LcaRunDriver.ts",
        _driver_ts(),
    )

    executor = "src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts"
    text = ctx.read(executor)
    if "runLcaJournal" not in text:
        text = ctx.replace_first_of(executor, _IMPORT_REPLACEMENTS, label="lca_run_driver import")
        ctx.write(executor, text)
        text = ctx.replace_first_of(executor, _MODEL_REPLACEMENTS, label="lca_run_driver model")
        ctx.write(executor, text)
        changed = True

    for rel in _STALE:
        path = ctx.path(rel)
        if path.is_file():
            path.unlink()
            changed = True
    return changed
