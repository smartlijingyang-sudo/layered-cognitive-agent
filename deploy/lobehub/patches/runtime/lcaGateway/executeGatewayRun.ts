// LCA-P1: streamingExecutor entry when gateway mode is enabled.
//
// Called from streamingExecutor.ts (patched by lca_runtime_agent_gateway) when
// isLcaGatewayMode() is true. Starts the run via POST /lca-api/runs,
// then opens the LCA agent-gateway WebSocket and wires native gateway events.

import type { ConversationContext } from '@lobechat/types';
import { countContextTokens, getSlicedMessages } from '@lobechat/context-engine';

import { getAiInfraStoreState } from '@/store/aiInfra';
import { modelContextWindowTokens } from '@/store/aiInfra/slices/aiModel/selectors';
import { useAgentStore } from '@/store/agent';
import { buildRunLifecycle } from '@/store/chat/slices/agentRun/actions/lifecycle/buildRunLifecycle';
import type { RunScope } from '@/store/chat/slices/agentRun/actions/lifecycle/types';
import { createGatewayEventRouter } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventRouter';
import { dbMessageSelectors } from '@/store/chat/slices/message/selectors/dbMessage';
import type { ChatStore } from '@/store/chat/store';
import { messageMapKey } from '@/store/chat/utils/messageMapKey';

import { appendDeliverableClosure } from '../lcaArtifacts';
import { persistAssistantRow } from '../lcaPersist';
import { getLcaGatewayUrl } from './client';
import { createLcaDeliverables, type LcaDeliverables } from './deliverables';
import { createLcaGatewayEventHandler } from './event_handler';
import { lcaStartRun } from './execute';
import { lcaRefreshWsToken } from './reconnect';

type MessageLike = { id?: string; parentId?: string; role?: string };

/** Walk assistant-anchored children from the seed placeholder (native spine). */
function collectAssistantChain<T extends { id: string; parentId?: string | null; role?: string }>(
  messages: T[],
  seedId: string,
): T[] {
  const byParent = new Map<string, Array<(typeof messages)[number]>>();
  for (const message of messages) {
    if (message.role !== 'assistant' || !message.parentId) continue;
    const siblings = byParent.get(message.parentId) ?? [];
    siblings.push(message);
    byParent.set(message.parentId, siblings);
  }
  const seed = messages.find((message) => message.id === seedId);
  if (!seed) return [];
  const chain = [seed];
  const seen = new Set<string>([seedId]);
  let cursor = seedId;
  while (true) {
    const next = (byParent.get(cursor) ?? []).find((message) => !seen.has(message.id));
    if (!next) break;
    chain.push(next);
    seen.add(next.id);
    cursor = next.id;
  }
  return chain;
}

/** Map a user-turn parent id to the assistant placeholder LobeHub created for this reply. */
function resolveAssistantMessageId(
  parentMessageId: string | undefined,
  parentMessageType: string | undefined,
  messages: MessageLike[],
  nested: Record<string, unknown>,
): string {
  const findAssistantForUser = (userId: string): string | undefined =>
    messages.find((m) => m.role === 'assistant' && m.parentId === userId)?.id;

  const userMessageId =
    typeof nested.userMessageId === 'string' ? nested.userMessageId : undefined;

  if (parentMessageId) {
    const parentRow = messages.find((m) => m.id === parentMessageId);
    if (parentRow?.role === 'user') {
      return findAssistantForUser(parentMessageId) ?? parentMessageId;
    }
    if (parentMessageType === 'assistant' || parentRow?.role === 'assistant') {
      return parentMessageId;
    }
    if (parentMessageType === 'user') {
      return findAssistantForUser(parentMessageId) ?? parentMessageId;
    }
  }

  if (userMessageId) {
    return findAssistantForUser(userMessageId) ?? parentMessageId ?? '';
  }

  return parentMessageId ?? '';
}

/**
 * Shared terminal-cleanup closure for LCA gateway runs (initial run AND
 * askUserQuestion resume). Persists the streamed assistant chain, folds
 * harvested sandbox files onto the answer row, and resets the topic status.
 */
function createLcaRunOnSessionComplete(
  get: () => ChatStore,
  params: {
    assistantMessageId: string;
    context: ConversationContext;
    deliverables: LcaDeliverables;
    gatewayOpId: string;
    model: string;
    topicId: string;
  },
): (info: { authFailed: boolean; succeeded: boolean; terminalReceived: boolean }) => void {
  const { assistantMessageId, context, deliverables, gatewayOpId, model, topicId } = params;

  return ({ terminalReceived, authFailed, succeeded }) => {
    const state = get();
    if (!terminalReceived) state.completeOperation(gatewayOpId);
    if (authFailed) state.completeOperation(gatewayOpId);
    if (terminalReceived && succeeded && assistantMessageId) {
      const seed = dbMessageSelectors.getDbMessageById(assistantMessageId)(get());
      const topicMessages =
        get().dbMessagesMap[messageMapKey({ agentId: context.agentId, topicId })] ?? [];
      const chain = collectAssistantChain(topicMessages, assistantMessageId);
      const rows = chain.length > 0 ? chain : seed ? [seed] : [];
      // Harvested sandbox files ride the tool cards; the answer row is the
      // one place a user expects the download list, so the turn's last
      // persisted row carries it — as a native card, and as markdown in the
      // answer text, because LobeHub only persists file rows it owns.
      const harvested = deliverables.files();
      const { fileList, imageList } = deliverables.lists();
      const answerRowId = rows
        .findLast((msg) => {
          const text = typeof msg.content === 'string' ? msg.content : '';
          return Boolean(msg.reasoning?.content || text || msg.tools?.length);
        })?.id;
      for (const msg of rows) {
        const text = typeof msg.content === 'string' ? msg.content : '';
        const tools = msg.tools;
        if (!(msg.reasoning?.content || text || tools?.length)) continue;
        const isAnswerRow = msg.id === answerRowId;
        void persistAssistantRow(get, msg.id, {
          content: isAnswerRow ? appendDeliverableClosure(text, harvested) : text,
          model,
          operationId: gatewayOpId,
          ...(msg.reasoning ? { reasoning: msg.reasoning } : {}),
          ...(tools?.length ? { tools } : {}),
          ...(isAnswerRow && fileList.length ? { fileList } : {}),
          ...(isAnswerRow && imageList.length ? { imageList } : {}),
        }).catch(console.error);
      }
    }
    if (topicId) {
      const viewing = state.activeTopicId === topicId;
      if (viewing || !succeeded) {
        void state.updateTopicStatus?.({
          agentId: context.agentId,
          groupId: context.groupId,
          status: 'active',
          topicId,
        });
      }
    }
  };
}

// ADR-0244 D1: placeholder-free, token-budget-aware wire messages.
const ASSISTANT_PLACEHOLDER = '...';
const LOADING_FLAT = 'LOADING_FLAT';

type AttachmentExtras = {
  imageList?: Array<{ id: string; url: string; alt?: string }>;
  fileList?: Array<{ id: string; name?: string; url?: string; fileType?: string }>;
  files?: string[];
};

type WireMessage = { role: string; content: string } & AttachmentExtras;

function isPlaceholderAssistantRow(m: unknown): boolean {
  const row = m as {
    role?: string;
    content?: unknown;
    tools?: unknown[];
    reasoning?: { content?: unknown };
    imageList?: unknown[];
    fileList?: unknown[];
  };
  if (!row || row.role !== 'assistant') return false;
  if (row.tools?.length || row.reasoning?.content || row.imageList?.length || row.fileList?.length) {
    return false;
  }
  const content = typeof row.content === 'string' ? row.content : '';
  return content === '' || content === ASSISTANT_PLACEHOLDER || content === LOADING_FLAT;
}

function toWireMessage(m: unknown): WireMessage | null {
  const row = m as {
    role?: string;
    content?: unknown;
    imageList?: unknown[];
    fileList?: unknown[];
    files?: string[];
  };
  if (!row || row.role === 'system') return null;
  if (row.role !== 'user' && row.role !== 'assistant') return null;

  const content =
    typeof row.content === 'string'
      ? row.content
      : row.content != null
        ? JSON.stringify(row.content)
        : '';

  const attachmentExtras: AttachmentExtras = {};
  if (Array.isArray(row.imageList) && row.imageList.length > 0) {
    attachmentExtras.imageList = row.imageList as AttachmentExtras['imageList'];
  }
  if (Array.isArray(row.fileList) && row.fileList.length > 0) {
    attachmentExtras.fileList = row.fileList as AttachmentExtras['fileList'];
  }
  if (Array.isArray(row.files) && row.files.length > 0) {
    attachmentExtras.files = row.files as string[];
  }

  if (!content && Object.keys(attachmentExtras).length === 0) return null;
  return { role: row.role, content, ...attachmentExtras };
}

/**
 * Build the ``messages`` payload for POST /lca-api/runs.
 *
 * Drops assistant placeholder rows, keeps attachments on their originating
 * turn, and truncates history to the model context window when one is known.
 * The current turn is always preserved. Falls back to an empty user message
 * when nothing remains.
 */
export function sliceWireMessages(rawMessages: unknown[], ctxWindow?: number): WireMessage[] {
  const filtered = rawMessages.filter((m) => !isPlaceholderAssistantRow(m));
  const toWire = (messages: unknown[]) =>
    messages.map(toWireMessage).filter((m): m is WireMessage => m !== null);

  if (filtered.length === 0 || toWire(filtered).length === 0) {
    return [{ role: 'user', content: '' }];
  }
  if (!ctxWindow || ctxWindow <= 0) return toWire(filtered);

  const reserved = Math.floor(ctxWindow * 0.4);
  const budget = ctxWindow - reserved;
  // Count tokens on the original UI messages so the context engine sees the
  // real content structure, not the flattened wire projection.
  const count = (messages: unknown[]) =>
    countContextTokens({ messages: messages as never, tools: [] }).adjustedTotal;

  if (count(filtered) <= budget) return toWire(filtered);

  // Group-aware truncation: keep the largest suffix that fits the budget.
  let lo = 1;
  let hi = filtered.length;
  let best = 1;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const sliced = getSlicedMessages(filtered as never, {
      enableHistoryCount: true,
      historyCount: mid,
    }) as unknown[];
    if (sliced.length > 0 && count(sliced) <= budget) {
      best = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  const finalSliced = getSlicedMessages(filtered as never, {
    enableHistoryCount: true,
    historyCount: best,
  }) as unknown[];
  return toWire(finalSliced);
}

export async function lcaExecuteGatewayRun(
  get: () => ChatStore,
  params: {
    context: unknown;
    messages: Array<{
      role: string;
      content: unknown;
      imageList?: Array<{ id: string; url: string; alt?: string }>;
      fileList?: Array<{ id: string; name?: string; url?: string; fileType?: string }>;
      files?: string[];
    }>;
    model: string;
    operationId?: string;
    parentMessageId?: string;
    parentMessageType?: string;
    scope: string;
    params: Record<string, unknown>;
  },
): Promise<{ model: string; provider: string }> {
  // ADR-0244 D1: budget-aware, placeholder-free wire messages.
  const state = get();
  const context = params.context as ConversationContext;
  const topicId = context.topicId ?? state.activeTopicId ?? '';
  const nested = params.params;

  const agentRow = useAgentStore.getState().agentMap[context.agentId] as
    | { model?: string | null; provider?: string | null }
    | undefined;
  const ctxWindow =
    agentRow?.model && agentRow?.provider
      ? modelContextWindowTokens(agentRow.model, agentRow.provider)(getAiInfraStoreState())
      : undefined;
  const wireMessages = sliceWireMessages(params.messages || [], ctxWindow ?? undefined);

  const assistantMessageId = resolveAssistantMessageId(
    params.parentMessageId,
    params.parentMessageType,
    params.messages,
    nested,
  );

  // The LCA assistant row stores the backend assistant_id in
  // `agencyConfig.lcaAssistantId`; forward it so the run assembles the
  // agent persona from its Home (ADR-0242 D3). `params.model` is the run
  // mode ('solo'/'team'), so the agent row lookup uses `context.agentId`.
  const assistantId = (
    agentRow as { agencyConfig?: { lcaAssistantId?: string } | null } | undefined
  )?.agencyConfig?.lcaAssistantId;

  const receipt = await lcaStartRun({
    agent: { id: params.model, name: params.model },
    messages: wireMessages,
    parent_message_id: assistantMessageId || params.parentMessageId,
    topic_id: topicId || undefined,
    ...(assistantId ? { assistant_id: assistantId } : {}),
  });

  const { operationId: gatewayOpId } = state.startOperation({
    context,
    metadata: { serverOperationId: receipt.runId },
    ...(params.operationId ? { parentOperationId: params.operationId } : {}),
    type: 'execServerAgentRuntime',
  });

  if (assistantMessageId) {
    state.associateMessageWithOperation(assistantMessageId, gatewayOpId);
  }

  if (params.operationId) {
    state.completeOperation(params.operationId);
  }

  state.onOperationCancel(gatewayOpId, async () => {
    await fetch(`/lca-api/runs/${receipt.runId}/cancel`, {
      headers: { Authorization: `Bearer ${process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local'}` },
      method: 'POST',
    }).catch((err) => console.error('[LCA] cancel failed:', err));
  });

  const runScope: RunScope = params.scope === 'sub_agent' ? 'sub_agent' : 'top_level';
  const deliverables = createLcaDeliverables();
  const eventHandler = createLcaGatewayEventHandler(
    get,
    {
      assistantMessageId,
      context,
      gatewayOperationId: receipt.runId,
      operationId: gatewayOpId,
      runLifecycle: buildRunLifecycle(get, {
        context,
        parentMessageId: assistantMessageId,
        parentMessageType: 'assistant',
        runId: gatewayOpId,
        runScope,
        runtimeType: 'gateway',
      }),
    },
    deliverables,
  );

  const eventRouter = createGatewayEventRouter({
    createMemberHandler: () => () => undefined,
    ownerHandler: eventHandler,
    ownerOperationId: receipt.runId,
  });

  state.connectToGateway({
    gatewayUrl: getLcaGatewayUrl(),
    onEvent: eventRouter,
    onSessionComplete: createLcaRunOnSessionComplete(get, {
      assistantMessageId,
      context,
      deliverables,
      gatewayOpId,
      model: params.model,
      topicId,
    }),
    operationId: receipt.runId,
    token: receipt.token,
    topicId: topicId || undefined,
  });

  return { model: params.model, provider: 'openai' };
}

/**
 * Resume a parked LCA run after the user answers an askUserQuestion card.
 *
 * The answer ships as a `resume_tool_result` run command (POST /lca-api/runs
 * returns the SAME run_id — backend `_dispatch_resume`). A NEW gateway
 * operation reconnects to that run's WS from `lastEventId`, so steps 2..n and
 * the final answer reach the UI. This replaces the old `/answer` POST which
 * resumed the run server-side but never reopened the WS.
 */
export async function lcaResumeGatewayRun(
  get: () => ChatStore,
  params: {
    context: ConversationContext;
    runId: string;
    lastEventId: string;
    parentMessageId: string;
    topicId: string;
    toolCallId: string;
    content: string;
  },
): Promise<void> {
  const state = get();
  const { context, runId, lastEventId, parentMessageId, topicId, toolCallId, content } = params;

  // The tool message owns the question card; its parent is the assistant
  // message that called askUserQuestion. Fall back to the tool message id.
  const toolMessage = dbMessageSelectors.getDbMessageById(parentMessageId)(get());
  const assistantMessageId = toolMessage?.parentId || parentMessageId;

  // Resume through the native-aligned path: POST /lca-api/runs with
  // resume_tool_result returns the SAME run_id (backend _dispatch_resume).
  await lcaStartRun({
    agent: { id: 'solo', name: 'solo' },
    messages: [],
    parent_message_id: parentMessageId,
    topic_id: topicId || undefined,
    resume_tool_result: { content, parentMessageId, toolCallId },
  });

  // The resume receipt does not carry a fresh ws_token; mint one for this run.
  const token = await lcaRefreshWsToken(runId, 'lca-local');

  const { operationId: gatewayOpId } = state.startOperation({
    context,
    metadata: { serverOperationId: runId },
    type: 'execServerAgentRuntime',
  });

  if (assistantMessageId) {
    state.associateMessageWithOperation(assistantMessageId, gatewayOpId);
  }

  state.onOperationCancel(gatewayOpId, async () => {
    await fetch(`/lca-api/runs/${runId}/cancel`, {
      headers: { Authorization: `Bearer ${process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local'}` },
      method: 'POST',
    }).catch((err) => console.error('[LCA] cancel failed:', err));
  });

  const runScope: RunScope = context.scope === 'sub_agent' ? 'sub_agent' : 'top_level';
  const deliverables = createLcaDeliverables();
  const eventHandler = createLcaGatewayEventHandler(
    get,
    {
      assistantMessageId,
      context,
      gatewayOperationId: runId,
      operationId: gatewayOpId,
      resuming: true,
      runLifecycle: buildRunLifecycle(get, {
        context,
        parentMessageId: assistantMessageId,
        parentMessageType: 'assistant',
        runId: gatewayOpId,
        runScope,
        runtimeType: 'gateway',
      }),
    },
    deliverables,
  );

  const eventRouter = createGatewayEventRouter({
    createMemberHandler: () => () => undefined,
    ownerHandler: eventHandler,
    ownerOperationId: runId,
  });

  state.connectToGateway({
    gatewayUrl: getLcaGatewayUrl(),
    onEvent: eventRouter,
    onSessionComplete: createLcaRunOnSessionComplete(get, {
      assistantMessageId,
      context,
      deliverables,
      gatewayOpId,
      model: 'solo',
      topicId,
    }),
    operationId: runId,
    token,
    topicId: topicId || undefined,
    lastEventId,
  });
}
