// LCA-P1: unit test for the LCA gateway event handler factory.
//
// Copied into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/event_handler.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/event_handler.test.ts

import type { AgentStreamEvent } from '@lobechat/agent-gateway-client';
import type { ConversationContext, UIChatMessage } from '@lobechat/types';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { messageService } from '@/services/message';
import type { ChatStore } from '@/store/chat/store';
import { messageMapKey } from '@/store/chat/utils/messageMapKey';

import { createLcaGatewayEventHandler } from './event_handler';

const context = {
  agentId: 'agent-1',
  topicId: 'topic-1',
} as ConversationContext;

const makeEvent = (type: AgentStreamEvent['type'], data?: AgentStreamEvent['data']) =>
  ({
    data,
    id: 'event-1',
    operationId: 'op-1',
    stepIndex: 1,
    timestamp: 0,
    type,
  }) as AgentStreamEvent;

const topicKey = messageMapKey({ agentId: 'agent-1', topicId: 'topic-1' });

/** Seed row already in the store before the LCA stream begins. */
const seedRow = {
  content: '',
  id: 'step2-msg',
  model: 'gpt-4o',
  parentId: 'msg-user',
  provider: 'openai',
  role: 'assistant',
  topicId: 'topic-1',
} as unknown as UIChatMessage;

const createStore = (dbMessagesMap: Record<string, UIChatMessage[]> = { [topicKey]: [seedRow] }) =>
  ({
    activeAgentId: 'agent-1',
    activeTopicId: 'topic-1',
    associateMessageWithOperation: vi.fn(),
    completeOperation: vi.fn(),
    dbMessagesMap,
    internal_dispatchMessage: vi.fn(),
    internal_toggleToolCallingStreaming: vi.fn(),
    operations: {},
    replaceMessages: vi.fn(),
    startOperation: vi.fn(() => ({
      abortController: new AbortController(),
      operationId: 'reasoning-op',
    })),
    updateOperationMetadata: vi.fn(),
  }) as unknown as ChatStore;

const flush = async () => {
  for (let i = 0; i < 50; i += 1) await Promise.resolve();
};

describe('createLcaGatewayEventHandler', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('reconciles against the in-memory reader, not the DB service', async () => {
    // If the factory leaked the DB singleton into the handler, this spy would
    // observe the call. With the LCA reader in place, the handler resolves
    // `getMessages` from `dbMessagesMap` instead.
    const dbSpy = vi
      .spyOn(messageService, 'getMessages')
      .mockResolvedValue([
        { id: 'hollow-db-row', role: 'assistant' },
      ] as unknown as UIChatMessage[]);

    const store = createStore();
    const handler = createLcaGatewayEventHandler(() => store, {
      assistantMessageId: 'seed-msg',
      context,
      operationId: 'op-1',
    });

    // The "old server" branch (no `assistantMessage` seed) is what exercises
    // the LCA reader's reconciliation path. The native handler would call
    // `fetchAndReplaceMessages` here and overwrite streamed content with the
    // hollow row.
    handler(makeEvent('stream_start', { assistantMessage: undefined }));
    await flush();

    expect(dbSpy).not.toHaveBeenCalled();
    // The LCA reader returns the live store array — `replaceMessages` runs,
    // but it would carry the streamed content, never the hollow DB row.
    expect(store.replaceMessages).toHaveBeenCalledWith([seedRow], {
      context,
      preserveWorks: true,
    });
  });

  it('skips mid-stream DB refetches (tool_end / step_complete / agent_runtime_end)', async () => {
    const dbSpy = vi
      .spyOn(messageService, 'getMessages')
      .mockResolvedValue([] as unknown as UIChatMessage[]);

    const store = createStore();
    const handler = createLcaGatewayEventHandler(() => store, {
      assistantMessageId: 'seed-msg',
      context,
      operationId: 'op-1',
    });

    handler(makeEvent('tool_end', { isSuccess: true }));
    handler(makeEvent('step_complete', { phase: 'execution_complete' }));
    handler(makeEvent('agent_runtime_end', { reason: 'completed' }));
    await flush();

    // `shouldSkipMidStreamMessageFetch` returns true under `runtimeType:
    // 'lca-gateway'`, so these three branches must NOT call into any reader.
    // The LCA reader would otherwise be called too — what we are pinning here
    // is that the LCA path short-circuits BEFORE the fetch.
    expect(dbSpy).not.toHaveBeenCalled();
  });
});
