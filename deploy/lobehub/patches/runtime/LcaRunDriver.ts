import type {
  ChatMessageError,
  ChatToolPayload,
  ChatToolPayloadWithResult,
  MessageToolCall,
  UIChatMessage,
} from '@lobechat/types';

import { dbMessageSelectors } from '@/store/chat/slices/message/selectors/dbMessage';
import type { ChatStore } from '@/store/chat/store';
import { useAgentStore } from '@/store/agent';
import { agentByIdSelectors } from '@/store/agent/selectors';

import { StreamingHandler } from '../StreamingHandler';
import {
  collectArtifactFiles,
  latestDeliverables,
  mimeFromName,
  rewriteArtifactMarkdown,
  toFileList,
  toImageList,
  type ArtifactFile,
} from './lcaArtifacts';
import { persistMissed, snapshotRow, type ProjectedRow } from './lcaChatRow';
import { toLcaChatMessageError } from './lcaError';
import {
  parseSseBlock,
  projectJournalFrame,
  toolCallId,
  type JournalFrame,
  type Projected,
} from './lcaJournal';
import { persistAssistantRow } from './lcaPersist';
import { WIRE } from './lcaWire';

const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
const TERMINAL = new Set(['canceled', 'completed', 'failed']);

const RESULT_KEYS = new Set([
  'success',
  'executionEnv',
  'stdout',
  'stderr',
  'output',
  'exitCode',
  'exit_code',
  'error',
  'errorDetail',
  'files',
  'downloadUrl',
  'filename',
  'mimeType',
  'size',
  'sizeBytes',
  'hasResources',
  'source',
  'title',
  'resources',
  'resultNumbers',
  'results',
  'previewable',
  'attachmentId',
  'url',
]);

type WireFile = { id?: string; mime_type?: string; name: string; size?: number; url: string };

type TurnTool = {
  call: MessageToolCall;
  operationId?: string;
  result?: ChatToolPayloadWithResult['result'];
  resultMsgId?: string;
};

function pickArgs(state: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!state) return {};
  const args: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(state)) {
    if (!RESULT_KEYS.has(key)) args[key] = value;
  }
  return args;
}

function toolCardContent(state: Record<string, unknown>): string {
  for (const key of ['content', 'output', 'stdout'] as const) {
    const value = state[key];
    if (typeof value === 'string' && value) return value;
  }
  return '';
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

function hrefFile(name: string, url: string): ArtifactFile {
  const mimeType = mimeFromName(name);
  return {
    mimeType,
    name,
    previewable: mimeType.startsWith('image/') || mimeType === 'application/pdf',
    url,
  };
}

export function planeFieldsFromAgent(agentId: string | undefined): {
  device_id?: string;
  plane?: string;
  execution_target?: string;
} {
  if (!agentId) return {};
  const config = agentByIdSelectors.getAgencyConfigById(agentId)(useAgentStore.getState());
  const target = config?.executionTarget;
  const deviceId = config?.boundDeviceId;
  if (target === 'local' || target === 'device') {
    return deviceId
      ? { device_id: deviceId, plane: 'machine', execution_target: 'device' }
      : { plane: 'machine', execution_target: 'device' };
  }
  if (target === 'sandbox') return { plane: 'sandbox', execution_target: 'sandbox' };
  if (target === 'auto') return { execution_target: 'auto' };
  if (target === 'none') return { execution_target: 'none' };
  return {};
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
  let rowError: ChatMessageError | undefined;
  let firstReuse = options.reuseAssistantId;
  let handler: StreamingHandler | null = null;
  let journalDurationMs: number | undefined;
  let lastResultMsgId: string | null = null;
  const tools = new Map<string, TurnTool>();
  const currentTurnTools: TurnTool[] = [];
  const hrefs = new Map<string, string>();

  const hrefFiles = (): ArtifactFile[] =>
    [...hrefs.entries()].map(([name, url]) => hrefFile(name, url));

  const rememberHref = (name: string, url: string) => {
    const base = name.split(/[/\\]/).at(-1) || name;
    if (base && url) hrefs.set(base, url);
  };

  const dispatchMessage = (id: string, value: Record<string, unknown>) => {
    get().internal_dispatchMessage(
      { id, type: 'updateMessage', value },
      { operationId: options.operationId },
    );
  };

  const resolveTurnTools = (): ChatToolPayload[] => {
    if (!currentTurnTools.length) return [];
    const payloads = get().internal_transformToolCalls(currentTurnTools.map((item) => item.call));
    for (const payload of payloads) {
      const rec = currentTurnTools.find((item) => item.call.id === payload.id);
      if (!rec) continue;
      if (rec.result) (payload as { result?: typeof rec.result }).result = rec.result;
      if (rec.resultMsgId) payload.result_msg_id = rec.resultMsgId;
    }
    return payloads;
  };

  const rewritten = (text: string) => rewriteArtifactMarkdown(text, hrefFiles());

  const currentRow = (): ProjectedRow =>
    snapshotRow(
      assistantId,
      rewritten(handler?.getOutput() ?? ''),
      resolveTurnTools().length,
      Boolean(handler?.getThinkingContent()),
      rowError,
    );

  const publishTurnTools = (streaming: boolean) => {
    if (!assistantId) return;
    const payloads = resolveTurnTools();
    if (!payloads.length) return;
    get().internal_toggleToolCallingStreaming(
      assistantId,
      payloads.map((payload) => {
        const rec = currentTurnTools.find((item) => item.call.id === payload.id);
        return streaming && !rec?.result;
      }),
    );
    dispatchMessage(assistantId, { tools: payloads });
  };

  const findTurnTool = (payload: Record<string, unknown>): TurnTool | undefined => {
    const id = toolCallId(payload, '');
    if (id && tools.has(id)) return tools.get(id);
    if (id) return undefined;
    return currentTurnTools.at(-1);
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
        onContentUpdate: (content, reasoning) =>
          dispatchMessage(messageId, {
            content: rewritten(content),
            reasoning,
          }),
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
        onToolCallsUpdate: (next) => dispatchMessage(messageId, { tools: next }),
        toggleToolCallingStreaming: (id, streaming) =>
          get().internal_toggleToolCallingStreaming(id, streaming),
        transformToolCalls: (calls) => get().internal_transformToolCalls(calls),
        uploadBase64Image: async () => ({}),
      },
    );

  const noteRowError = (error: unknown) => {
    const payload = toLcaChatMessageError(error);
    if (payload.message) rowError = payload;
  };

  const persistRow = async () => {
    if (!assistantId) return;
    const content = rewritten(handler?.getOutput() ?? '');
    const thinking = handler?.getThinkingContent() ?? '';
    const duration = journalDurationMs ?? handler?.getThinkingDuration();
    const turnTools = resolveTurnTools();
    const deliverables = turnTools.length === 0 ? latestDeliverables(hrefFiles()) : [];
    const imageList = toImageList(deliverables);
    const fileList = toFileList(deliverables);
    await persistAssistantRow(get, assistantId, {
      content,
      ...(rowError ? { error: rowError } : {}),
      ...(fileList.length ? { fileList } : {}),
      ...(imageList.length ? { imageList } : {}),
      model: options.model,
      operationId: options.operationId,
      ...(thinking
        ? { reasoning: { content: thinking, ...(duration !== undefined ? { duration } : {}) } }
        : {}),
      ...(turnTools.length ? { tools: turnTools } : {}),
    });
  };

  const sealOpenTools = () => {
    let dirty = false;
    for (const rec of currentTurnTools) {
      if (rec.result) continue;
      rec.result = { content: '', id: rec.call.id, state: {} };
      if (rec.operationId) {
        get().completeOperation(rec.operationId);
        rec.operationId = undefined;
      }
      dirty = true;
    }
    if (dirty) publishTurnTools(false);
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
      toolCalls: currentTurnTools.map((item) => item.call),
      type: 'stop',
    });
    handler = null;
  };

  const finishTurn = async () => {
    sealOpenTools();
    await sealRow();
    await finishHandler();
  };

  const publishFinalDeliverables = () => {
    if (!assistantId) return;
    const files = latestDeliverables(hrefFiles());
    if (!files.length) return;
    const imageList = toImageList(files);
    const fileList = toFileList(files);
    if (!imageList.length && !fileList.length) return;
    dispatchMessage(assistantId, {
      ...(fileList.length ? { fileList } : {}),
      ...(imageList.length ? { imageList } : {}),
    });
  };

  const openRow = async (nextSpeaker: string, parentId: string) => {
    speaker = nextSpeaker;
    let id = firstReuse;
    firstReuse = undefined;
    if (!id) {
      const created = await get().optimisticCreateMessage(
        {
          content: '',
          model: options.model,
          parentId,
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
    journalDurationMs = undefined;
    currentTurnTools.length = 0;
    get().associateMessageWithOperation(id, options.operationId);
    handler = makeHandler(id);
  };

  const openTurn = async (nextSpeaker: string) => {
    const sameSpeaker = !nextSpeaker || !speaker || nextSpeaker === speaker;
    const prevAssistant = assistantId;
    if (assistantId) await finishTurn();
    if (!sameSpeaker) lastResultMsgId = null;
    const userParent = options.userMessageId || options.parentMessageId;
    await openRow(
      nextSpeaker,
      sameSpeaker ? lastResultMsgId || prevAssistant || userParent : userParent,
    );
  };

  const ensureTurn = async () => {
    if (!assistantId) await openRow(speaker, options.userMessageId || options.parentMessageId);
    if (!handler) handler = makeHandler(assistantId);
  };

  const applyProjected = async (projected: Projected): Promise<void> => {
    switch (projected.kind) {
      case 'open-turn': {
        await openTurn(projected.speaker);
        return;
      }
      case 'reasoning': {
        await ensureTurn();
        handler?.handleChunk({ text: projected.text, type: 'reasoning' });
        return;
      }
      case 'reasoning-end': {
        if (projected.durationMs !== undefined) journalDurationMs = projected.durationMs;
        handler?.handleChunk({ type: 'stop' });
        if (assistantId && journalDurationMs !== undefined) {
          const thinking = handler?.getThinkingContent() ?? '';
          if (thinking) {
            dispatchMessage(assistantId, {
              reasoning: { content: thinking, duration: journalDurationMs },
            });
          }
        }
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
        const existing = tools.get(projected.idHint);
        if (existing) {
          existing.call.function.arguments = JSON.stringify(pickArgs(projected.state));
          handler?.handleChunk({
            isAnimationActives: currentTurnTools.map((item) => !item.result),
            tool_calls: currentTurnTools.map((item) => item.call),
            type: 'tool_calls',
          });
          if (existing.resultMsgId) {
            dispatchMessage(existing.resultMsgId, {
              plugin: {
                apiName: coords.apiName,
                arguments: existing.call.function.arguments,
                identifier: coords.identifier,
                id: existing.call.id,
                type: 'builtin',
              },
            });
          }
          publishTurnTools(!existing.result);
          return;
        }
        const call: MessageToolCall = {
          function: {
            arguments: JSON.stringify(pickArgs(projected.state)),
            name: `${coords.identifier}____${coords.apiName}`,
          },
          id: projected.idHint,
          type: 'function',
        };
        const rec: TurnTool = { call };
        tools.set(call.id, rec);
        currentTurnTools.push(rec);
        handler?.handleChunk({
          isAnimationActives: currentTurnTools.map((item) => !item.result),
          tool_calls: currentTurnTools.map((item) => item.call),
          type: 'tool_calls',
        });
        const payloads = resolveTurnTools();
        const plugin = payloads.find((item) => item.id === call.id);
        const created = await get().optimisticCreateMessage(
          {
            content: '',
            parentId: assistantId,
            plugin: plugin ?? {
              apiName: coords.apiName,
              arguments: call.function.arguments,
              identifier: coords.identifier,
              id: call.id,
              type: 'builtin',
            },
            role: 'tool',
            tool_call_id: call.id,
            topicId: ctx.topicId,
            ...(ctx.agentId ? { agentId: ctx.agentId } : {}),
            ...(ctx.threadId ? { threadId: ctx.threadId } : {}),
          },
          { operationId: options.operationId },
        );
        rec.resultMsgId = created?.id;
        lastResultMsgId = created?.id || lastResultMsgId;
        const { operationId: toolOpId } = get().startOperation({
          context: {
            agentId: ctx.agentId!,
            groupId: ctx.groupId,
            messageId: assistantId,
            threadId: ctx.threadId,
            topicId: ctx.topicId,
          },
          metadata: {
            apiName: coords.apiName,
            identifier: coords.identifier,
            startTime: Date.now(),
            tool_call_id: call.id,
          },
          parentOperationId: options.operationId,
          type: 'toolCalling',
        });
        rec.operationId = toolOpId;
        get().associateMessageWithOperation(assistantId, toolOpId);
        if (created?.id) get().associateMessageWithOperation(created.id, toolOpId);
        publishTurnTools(true);
        await persistRow();
        return;
      }
      case 'sandbox-delta': {
        const rec = findTurnTool(projected.payload);
        if (!rec) return;
        const prev = (rec.result?.state as Record<string, unknown> | undefined) ?? {};
        const field = projected.stream === 'stderr' ? 'stderr' : 'output';
        const nextState = {
          ...prev,
          [field]: `${String(prev[field] ?? '')}${projected.text}`,
        };
        rec.result = {
          ...rec.result,
          content: rec.result?.content ?? '',
          id: rec.call.id,
          state: nextState,
        };
        if (rec.resultMsgId) {
          get().internal_dispatchMessage(
            { id: rec.resultMsgId, key: field, type: 'updatePluginState', value: nextState[field] },
            { operationId: options.operationId },
          );
        }
        publishTurnTools(true);
        return;
      }
      case 'tool-invoked': {
        const rec = findTurnTool(projected.payload);
        if (!rec) {
          console.warn('lca: tool-invoked with no start', projected.payload);
          return;
        }
        const files = collectArtifactFiles(projected.files, projected.state.files);
        for (const file of files) rememberHref(file.name, file.url);
        const downloadUrl =
          typeof projected.state.downloadUrl === 'string' ? projected.state.downloadUrl : '';
        const filename = typeof projected.state.filename === 'string' ? projected.state.filename : '';
        if (filename && downloadUrl) rememberHref(filename, downloadUrl);
        const state = files.length ? { ...projected.state, files } : projected.state;
        rec.result = {
          content: toolCardContent(state),
          error: projected.payload.ok === false ? String(projected.payload.error ?? '') : undefined,
          id: rec.call.id,
          state,
        };
        if (rec.resultMsgId) {
          await get().optimisticUpdateMessageContent(
            rec.resultMsgId,
            rec.result.content || '',
            undefined,
            { operationId: options.operationId },
          );
          await get().optimisticUpdatePluginState(rec.resultMsgId, state, {
            operationId: options.operationId,
          });
        }
        if (rec.operationId) {
          if (projected.payload.ok === false) {
            get().failOperation(rec.operationId, {
              message: String(projected.payload.error ?? 'tool failed'),
              type: 'ToolExecutionError',
            });
          } else {
            get().completeOperation(rec.operationId);
          }
          rec.operationId = undefined;
        }
        lastResultMsgId = rec.resultMsgId || lastResultMsgId;
        publishTurnTools(false);
        await persistRow();
        return;
      }
      case 'tool-denied': {
        const rec = findTurnTool(projected.payload);
        if (!rec) return;
        rec.result = {
          content: '',
          error: projected.reason,
          id: rec.call.id,
          state: {},
        };
        if (rec.resultMsgId) {
          await get().optimisticUpdateMessageContent(rec.resultMsgId, '', undefined, {
            operationId: options.operationId,
          });
        }
        if (rec.operationId) {
          get().failOperation(rec.operationId, {
            message: projected.reason,
            type: 'ToolExecutionError',
          });
          rec.operationId = undefined;
        }
        lastResultMsgId = rec.resultMsgId || lastResultMsgId;
        publishTurnTools(false);
        await persistRow();
        return;
      }
      case 'run-finished': {
        if (projected.error) noteRowError(projected.error);
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

  const authHeaders = { Authorization: `Bearer ${LCA_TOKEN}` };

  try {
    const createRes = await fetch('/lca-api/runs', {
      body: JSON.stringify({
        agent: {
          id: ctx.agentId || 'solo',
          name: ctx.agentId ? String(ctx.agentId) : '助手',
        },
        messages: toWireMessages(options.messages),
        model: options.model,
        ...planeFieldsFromAgent(ctx.agentId),
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
      if (runId) {
        await fetch(`/lca-api/runs/${runId}/cancel`, {
          headers: authHeaders,
          method: 'POST',
        }).catch(() => undefined);
      }
      await finishTurn();
      publishFinalDeliverables();
      return currentRow();
    }
    noteRowError(error);
    await ensureTurn();
    await finishTurn();
    publishFinalDeliverables();
    return currentRow();
  }
  await finishTurn();
  publishFinalDeliverables();
  return currentRow();
}
