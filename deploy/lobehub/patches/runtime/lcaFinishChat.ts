import type { ConversationContext } from '@lobechat/types';

import { buildRunLifecycle } from '@/store/chat/slices/agentRun/actions/lifecycle/buildRunLifecycle';
import type { RunScope } from '@/store/chat/slices/agentRun/actions/lifecycle/types';
import { dbMessageSelectors } from '@/store/chat/slices/message/selectors/dbMessage';
import type { ChatStore } from '@/store/chat/store';

import { persistMissed, type ProjectedRow } from './lcaChatRow';

export type FinishLcaChatParams = {
  context: ConversationContext;
  operationId: string;
  parentMessageId: string;
  parentMessageType: 'user' | 'assistant' | 'tool';
  projected: ProjectedRow;
  scope?: string;
};

/**
 * LobeHub chrome after an LCA Run: stop the spinner, drain the send
 * queue, flip topic status, desktop notify. Not AgentRuntime.
 */
export async function finishLcaChat(get: () => ChatStore, params: FinishLcaChatParams): Promise<void> {
  const runScope: RunScope = params.scope === 'sub_agent' ? 'sub_agent' : 'top_level';
  const lifecycle = buildRunLifecycle(get, {
    context: params.context,
    parentMessageId: params.parentMessageId,
    parentMessageType: params.parentMessageType,
    runId: params.operationId,
    runScope,
    runtimeType: 'client',
  });
  const cancelled = get().operations[params.operationId]?.status === 'cancelled';
  const completeEvent = {
    context: params.context,
    operationId: params.operationId,
    runId: params.operationId,
    runScope,
    runtimeType: 'client' as const,
    runtimeStatus: cancelled ? 'interrupted' : params.projected.error ? 'error' : 'done',
  };
  const { requeued } = await lifecycle.completeRun(completeEvent);
  if (!requeued) await lifecycle.afterRunComplete(completeEvent);

  const stored = params.projected.assistantId
    ? dbMessageSelectors.getDbMessageById(params.projected.assistantId)(get())
    : undefined;
  if (persistMissed(params.projected, stored)) {
    console.error('lca: assistant row still hollow after run', {
      assistantId: params.projected.assistantId,
      memoryChars: params.projected.content.length,
      storedChars: typeof stored?.content === 'string' ? stored.content.length : 0,
      tools: params.projected.toolCount,
    });
  }
}
