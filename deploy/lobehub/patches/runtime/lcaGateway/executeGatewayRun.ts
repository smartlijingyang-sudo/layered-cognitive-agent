// LCA-P1: streamingExecutor entry when gateway mode is enabled.
//
// Called from streamingExecutor.ts (patched by lca_run_driver) when
// isLcaGatewayMode() is true. Starts the run via POST /lca-api/runs,
// then hands off to the native chat-store gateway connect path.

import { lcaStartRun } from './execute';

type ChatGet = () => Record<string, unknown>;

export async function lcaExecuteGatewayRun(
  get: ChatGet,
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
  const topicId =
    typeof state.activeTopicId === 'string' ? state.activeTopicId : '';

  const receipt = await lcaStartRun({
    agent: { id: params.model, name: params.model },
    messages: [{ role: 'user', content }],
    parent_message_id: params.parentMessageId,
    topic_id: topicId || undefined,
  });

  const connect =
    (state.connectToGatewayOperation as
      | ((args: Record<string, unknown>) => Promise<void>)
      | undefined) ??
    (state.reconnectToGatewayOperation as
      | ((args: Record<string, unknown>) => Promise<void>)
      | undefined);

  if (typeof connect !== 'function') {
    throw new Error(
      'chat store missing connectToGatewayOperation / reconnectToGatewayOperation',
    );
  }

  await connect({
    assistantMessageId: params.parentMessageId ?? params.params?.parentMessageId,
    operationId: receipt.runId,
    scope: params.scope,
    threadId: params.params?.threadId,
    topicId,
    token: receipt.token,
  });

  return { model: params.model, provider: 'openai' };
}
