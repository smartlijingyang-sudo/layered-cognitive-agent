import type { ChatToolPayload, MessageToolCall, UIChatMessage } from '@lobechat/types';

import { dbMessageSelectors } from '@/store/chat/slices/message/selectors/dbMessage';
import type { ChatStore } from '@/store/chat/store';

import { StreamingHandler } from '../StreamingHandler';
import { persistMissed, snapshotRow, type ProjectedRow } from './lcaChatRow';
import { WIRE } from './lcaWire';

const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';

type JournalFrame = {
  event: string;
  seq?: number;
  eventPayload?: Record<string, unknown>;
  speaker?: string;
};

type Projected =
  | { kind: 'ignore' }
  | { kind: 'open-turn'; speaker: string }
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

type WireFile = { id?: string; mime_type?: string; name: string; size?: number; url: string };

function collectWireFiles(message: UIChatMessage): WireFile[] {
  const out: WireFile[] = [];
  for (const file of message.fileList ?? []) {
    if (!file?.url || file.inaccessible) continue;
    out.push({
      id: file.id,
      mime_type: file.fileType,
      name: file.name,
      size: file.size,
      url: file.url,
    });
  }
  for (const image of message.imageList ?? []) {
    if (!image?.url) continue;
    out.push({
      id: image.id,
      mime_type: 'image/png',
      name: image.alt || image.id,
      url: image.url,
    });
  }
  return out;
}

function toWireMessages(messages: UIChatMessage[]): {
  content: string;
  files?: WireFile[];
  role: string;
}[] {
  return messages
    .filter((message) => message.role === 'user' || message.role === 'assistant' || message.role === 'system')
    .map((message) => {
      const files = collectWireFiles(message);
      return {
        content: typeof message.content === 'string' ? message.content : '',
        role: message.role,
        ...(files.length ? { files } : {}),
      };
    });
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
    const scope =
      data.scope && typeof data.scope === 'object'
        ? (data.scope as Record<string, unknown>)
        : {};
    const seqFromId = Number(idLine);
    return {
      event: eventName,
      seq: typeof data.seq === 'number' ? data.seq : Number.isFinite(seqFromId) ? seqFromId : undefined,
      eventPayload: inner,
      speaker: typeof scope.agent_role === 'string' ? scope.agent_role : '',
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
      return { kind: 'open-turn', speaker: frame.speaker ?? '' };
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

export async function runLcaJournal(get: () => ChatStore, options: LcaRunOptions): Promise<ProjectedRow> {
  const operation = get().operations[options.operationId];
  if (!operation) throw new Error(`Operation not found: ${options.operationId}`);
  const signal = operation.abortController.signal;
  const ctx = operation.context;

  let afterSeq = 0;
  let lastSeq = 0;
  let runId = '';
  let assistantId = '';
  let speaker = '';
  let firstReuse = options.reuseAssistantId;
  let handler: StreamingHandler | null = null;
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

  const currentRow = (): ProjectedRow =>
    snapshotRow(
      assistantId,
      handler?.getOutput() ?? '',
      resolveTurnTools().length,
      Boolean(handler?.getThinkingContent()),
    );

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

  const persistRow = async () => {
    if (!assistantId) return;
    const content = handler?.getOutput() ?? '';
    const thinking = handler?.getThinkingContent() ?? '';
    const duration = handler?.getThinkingDuration();
    const tools = resolveTurnTools();
    await get().optimisticUpdateMessageContent(
      assistantId,
      content,
      {
        model: options.model,
        provider: 'openai',
        ...(thinking
          ? { reasoning: { content: thinking, ...(duration !== undefined ? { duration } : {}) } }
          : {}),
        ...(tools.length ? { tools } : {}),
      },
      { operationId: options.operationId },
    );
  };

  const sealRow = async () => {
    if (!assistantId) return;
    const memory = currentRow();
    await persistRow();
    const stored = dbMessageSelectors.getDbMessageById(assistantId)(get());
    if (persistMissed(memory, stored)) {
      console.warn('lca: persist missed, retrying', { assistantId });
      await persistRow();
    }
  };

  const finishHandler = async () => {
    if (!handler) return;
    await handler.handleFinish({
      toolCalls: turnTools.map((item) => item.call),
      type: 'stop',
    });
    handler = null;
  };

  const finishTurn = async () => {
    await sealRow();
    await finishHandler();
  };

  const openRow = async (nextSpeaker: string) => {
    speaker = nextSpeaker;
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

  const ensureSpeaker = async (nextSpeaker: string) => {
    const sameSpeaker = !nextSpeaker || !speaker || nextSpeaker === speaker;
    if (!assistantId) {
      await openRow(nextSpeaker);
      return;
    }
    if (sameSpeaker) {
      if (handler) {
        await persistRow();
        await finishHandler();
      }
      handler = makeHandler(assistantId);
      return;
    }
    await finishTurn();
    turnTools.length = 0;
    assistantId = '';
    await openRow(nextSpeaker);
  };

  const ensureTurn = async () => {
    if (!assistantId) await openRow(speaker);
    if (!handler) handler = makeHandler(assistantId);
  };

  const applyProjected = async (projected: Projected): Promise<void> => {
    switch (projected.kind) {
      case 'open-turn': {
        await ensureSpeaker(projected.speaker);
        return;
      }
      case 'reasoning': {
        await ensureTurn();
        handler?.handleChunk({ text: projected.text, type: 'reasoning' });
        return;
      }
      case 'text': {
        await ensureTurn();
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
        await persistRow();
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
        await persistRow();
        return;
      }
      case 'run-finished': {
        if (projected.error && assistantId) {
          dispatchMessage(assistantId, {
            error: { message: projected.error, type: 'AgentExecutionError' },
          });
        }
        await persistRow();
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
      agent: {
        id: ctx.agentId || 'solo',
        name: ctx.agentId ? String(ctx.agentId) : '助手',
      },
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
      return currentRow();
    }
    await finishTurn();
    throw error;
  }
  await finishTurn();
  return currentRow();
}
