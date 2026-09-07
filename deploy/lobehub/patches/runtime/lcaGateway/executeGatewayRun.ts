// LCA-P1: streamingExecutor entry when gateway mode is enabled.
//
// Called from streamingExecutor.ts (patched by lca_runtime_agent_gateway) when
// isLcaGatewayMode() is true. Starts the run via POST /lca-api/runs,
// then opens the LCA agent-gateway WebSocket and wires native gateway events.

import type { ConversationContext } from '@lobechat/types';

import { buildRunLifecycle } from '@/store/chat/slices/agentRun/actions/lifecycle/buildRunLifecycle';
import type { RunScope } from '@/store/chat/slices/agentRun/actions/lifecycle/types';
import { createGatewayEventRouter } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventRouter';
import type { ChatStore } from '@/store/chat/store';

import { getLcaGatewayUrl } from './client';
import { createLcaGatewayEventHandler } from './event_handler';
import { lcaStartRun } from './execute';

export async function lcaExecuteGatewayRun(
  get: () => ChatStore,
  params: {
    context: unknown;
    messages: Array<{ role: string; content: unknown }>;
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

  const state = get();
  const context = params.context as ConversationContext;
  const topicId = context.topicId ?? state.activeTopicId ?? '';
  const assistantMessageId = params.parentMessageId ?? '';

  const receipt = await lcaStartRun({
    agent: { id: params.model, name: params.model },
    messages: [{ role: 'user', content }],
    parent_message_id: params.parentMessageId,
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
  const eventHandler = createLcaGatewayEventHandler(get, {
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
  });

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
