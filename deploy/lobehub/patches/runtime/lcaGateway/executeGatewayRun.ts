// LCA-P1: streamingExecutor entry when gateway mode is enabled.
//
// Called from streamingExecutor.ts (patched by lca_runtime_agent_gateway) when
// isLcaGatewayMode() is true. Starts the run via POST /lca-api/runs,
// then opens the LCA agent-gateway WebSocket and wires native gateway events.

import type { ConversationContext } from '@lobechat/types';

import { buildRunLifecycle } from '@/store/chat/slices/agentRun/actions/lifecycle/buildRunLifecycle';
import type { RunScope } from '@/store/chat/slices/agentRun/actions/lifecycle/types';
import { createGatewayEventRouter } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventRouter';
import { dbMessageSelectors } from '@/store/chat/slices/message/selectors/dbMessage';
import type { ChatStore } from '@/store/chat/store';
import { messageMapKey } from '@/store/chat/utils/messageMapKey';

import { appendDeliverableClosure } from '../lcaArtifacts';
import { persistAssistantRow } from '../lcaPersist';
import { getLcaGatewayUrl } from './client';
import { createLcaDeliverables } from './deliverables';
import { createLcaGatewayEventHandler } from './event_handler';
import { lcaStartRun } from './execute';

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
  const lastUser = params.messages
    .slice()
    .reverse()
    .find((m) => m.role === 'user');
  const content =
    typeof lastUser?.content === 'string'
      ? lastUser.content
      : JSON.stringify(lastUser?.content ?? '');

  // Forward LobeHub-side attachment fields so LCA ingress can hydrate the
  // FileStore before composing the run prompt. Empty arrays are dropped to
  // keep the wire shape stable for text-only turns.
  const attachmentExtras: {
    imageList?: Array<{ id: string; url: string; alt?: string }>;
    fileList?: Array<{ id: string; name?: string; url?: string; fileType?: string }>;
    files?: string[];
  } = {};
  const imageList = (lastUser as { imageList?: unknown } | undefined)?.imageList;
  if (Array.isArray(imageList) && imageList.length > 0) {
    attachmentExtras.imageList = imageList as Array<{
      id: string;
      url: string;
      alt?: string;
    }>;
  }
  const fileList = (lastUser as { fileList?: unknown } | undefined)?.fileList;
  if (Array.isArray(fileList) && fileList.length > 0) {
    attachmentExtras.fileList = fileList as Array<{
      id: string;
      name?: string;
      url?: string;
      fileType?: string;
    }>;
  }
  const files = (lastUser as { files?: unknown } | undefined)?.files;
  if (Array.isArray(files) && files.length > 0) {
    attachmentExtras.files = files as string[];
  }

  const state = get();
  const context = params.context as ConversationContext;
  const topicId = context.topicId ?? state.activeTopicId ?? '';
  const nested = params.params;
  const assistantMessageId = resolveAssistantMessageId(
    params.parentMessageId,
    params.parentMessageType,
    params.messages,
    nested,
  );

  const receipt = await lcaStartRun({
    agent: { id: params.model, name: params.model },
    messages: [{ role: 'user', content, ...attachmentExtras }],
    parent_message_id: assistantMessageId || params.parentMessageId,
    topic_id: topicId || undefined,
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
    onSessionComplete: ({ terminalReceived, authFailed, succeeded }) => {
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
            model: params.model,
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
    },
    operationId: receipt.runId,
    token: receipt.token,
    topicId: topicId || undefined,
  });

  return { model: params.model, provider: 'openai' };
}
