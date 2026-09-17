// Persist one assistant step and its tool rows into LobeHub's message DB.
// Native call_llm / persistToolBatch do the same: assistant.tools[] is the
// call list; result.content / pluginState live on role=tool messages.

import { nanoid } from '@lobechat/utils';
import type { ConversationContext, UIChatMessage } from '@lobechat/types';

import { messageService } from '@/services/message';
import type { ChatStore } from '@/store/chat/store';
import { messageMapKey } from '@/store/chat/utils/messageMapKey';

export type LcaToolCalling = {
  apiName?: string;
  arguments?: string;
  id?: string;
  identifier?: string;
  result_msg_id?: string;
  type?: string;
};

const queryContext = (context: ConversationContext) => ({
  agentId: context.agentId,
  groupId: context.groupId,
  threadId: context.threadId,
  topicId: context.topicId,
});

const bucketKey = (store: ChatStore, context: ConversationContext) =>
  messageMapKey({
    ...context,
    agentId: context.agentId ?? store.activeAgentId,
    topicId: context.topicId !== undefined ? context.topicId : store.activeTopicId,
  });

const messagesIn = (store: ChatStore, context: ConversationContext): UIChatMessage[] =>
  store.dbMessagesMap[bucketKey(store, context)] ?? [];

const createInStore = (
  store: ChatStore,
  message: Record<string, unknown>,
  operationId: string,
  id: string,
) => {
  store.internal_dispatchMessage({ id, type: 'createMessage', value: message }, { operationId });
};

export const findChildAssistant = (
  store: ChatStore,
  context: ConversationContext,
  parentAssistantId: string,
): UIChatMessage | undefined =>
  messagesIn(store, context).find(
    (row) => row.role === 'assistant' && row.parentId === parentAssistantId,
  );

export const openLcaAssistantStep = (
  store: ChatStore,
  params: {
    context: ConversationContext;
    operationId: string;
    parentAssistantId: string;
  },
): { id: string } => {
  const id = nanoid();
  const parent = messagesIn(store, params.context).find((m) => m.id === params.parentAssistantId);
  const message = {
    agentId: params.context.agentId,
    content: '',
    id,
    model: parent?.model,
    parentId: params.parentAssistantId,
    provider: parent?.provider,
    role: 'assistant' as const,
    threadId: params.context.threadId,
    topicId: params.context.topicId ?? undefined,
  };
  createInStore(store, message, params.operationId, id);
  store.associateMessageWithOperation?.(id, params.operationId);
  store.internal_toggleToolCallingStreaming?.(params.parentAssistantId, undefined);
  void messageService.createMessage(message).catch(console.error);
  return { id };
};

export const ensureLcaToolMessages = (
  store: ChatStore,
  params: {
    assistantId: string;
    context: ConversationContext;
    operationId: string;
    toolsCalling: LcaToolCalling[];
  },
): LcaToolCalling[] => {
  const existing = messagesIn(store, params.context);
  const byCallId = new Map<string, UIChatMessage>();
  for (const row of existing) {
    if (row.role === 'tool' && typeof row.tool_call_id === 'string') {
      byCallId.set(row.tool_call_id, row);
    }
  }

  return params.toolsCalling.map((tool) => {
    const callId = tool.id;
    if (!callId) return tool;
    const already = byCallId.get(callId);
    if (already?.id) return { ...tool, result_msg_id: already.id };

    const toolMessageId = nanoid();
    const toolMessage = {
      agentId: params.context.agentId,
      content: '',
      id: toolMessageId,
      parentId: params.assistantId,
      plugin: {
        apiName: tool.apiName,
        arguments: tool.arguments,
        identifier: tool.identifier,
        type: tool.type,
      },
      role: 'tool' as const,
      threadId: params.context.threadId,
      tool_call_id: callId,
      topicId: params.context.topicId ?? undefined,
    };
    createInStore(store, toolMessage, params.operationId, toolMessageId);
    void messageService.createMessage(toolMessage).catch(console.error);
    return { ...tool, result_msg_id: toolMessageId };
  });
};

export const persistLcaToolResult = (
  store: ChatStore,
  params: {
    context: ConversationContext;
    operationId: string;
    result?: { content?: unknown; error?: unknown; state?: unknown };
    toolCallId: string;
  },
): void => {
  const toolRow = messagesIn(store, params.context).find(
    (row) => row.role === 'tool' && row.tool_call_id === params.toolCallId,
  );
  if (!toolRow) return;

  const content = typeof params.result?.content === 'string' ? params.result.content : undefined;
  const pluginState =
    params.result?.state && typeof params.result.state === 'object'
      ? (params.result.state as Record<string, unknown>)
      : undefined;
  const pluginError = params.result?.error;

  store.internal_dispatchMessage(
    {
      id: toolRow.id,
      type: 'updateMessage',
      value: {
        ...(content !== undefined ? { content } : {}),
        ...(pluginState ? { pluginState } : {}),
        ...(pluginError ? { pluginError } : {}),
      },
    },
    { operationId: params.operationId },
  );

  void messageService
    .updateToolMessage(
      toolRow.id,
      {
        ...(content !== undefined ? { content } : {}),
        ...(pluginState ? { pluginState } : {}),
        ...(pluginError ? { pluginError } : {}),
      },
      queryContext(params.context),
    )
    .catch(console.error);
};
