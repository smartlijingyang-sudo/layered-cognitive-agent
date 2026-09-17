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
    // Mirror the native gateway action surface so any stray
    // `internal_executeClientTool` invocation shows up in the spy. The LCA
    // factory is expected to drop `tool_execute` events before they reach the
    // shared handler — the spy must NOT be called.
    internal_executeClientTool: vi.fn().mockResolvedValue(undefined),
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
    vi.spyOn(messageService, 'createMessage').mockResolvedValue({ id: 'x', messages: [] } as never);
    vi.spyOn(messageService, 'updateToolMessage').mockResolvedValue({ success: true } as never);
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

  it('drops tool_execute events without invoking internal_executeClientTool', async () => {
    // The shared `gatewayEventHandler` switch carries a `case 'tool_execute':`
    // that forwards to `internal_executeClientTool` (used by the native hetero
    // path for client-executable tools). LCA's server-side runtime
    // (lobe-cloud-sandbox) executes tools itself and never emits
    // `tool_execute` on the wire — see event_translator.py (no handler) and
    // contracts/transport/agent_stream_event.py:188 (schema declared but
    // unused). The LCA factory must intercept and drop the event before the
    // shared switch sees it, so the spy here MUST NOT be called.
    const store = createStore();
    const handler = createLcaGatewayEventHandler(() => store, {
      assistantMessageId: 'seed-msg',
      context,
      gatewayOperationId: 'op-1',
      operationId: 'op-1',
    });

    handler(
      makeEvent('tool_execute', {
        apiName: 'local-shell',
        arguments: '{"cmd":"ls"}',
        identifier: 'local-system',
        toolCallId: 'call-x',
      }),
    );
    await flush();

    expect(store.internal_executeClientTool).not.toHaveBeenCalled();
  });

  it('folds tool_end file parts into the deliverable sink', async () => {
    const store = createStore();
    const collected: unknown[] = [];
    const handler = createLcaGatewayEventHandler(
      () => store,
      {
        assistantMessageId: 'seed-msg',
        context,
        operationId: 'op-1',
      },
      { collect: (result) => collected.push(result), lists: () => ({ fileList: [], imageList: [] }) },
    );

    const result = { content: 'ok', state: { files: [{ name: 'a.pdf', url: '/files/file_1' }] } };
    handler(makeEvent('tool_end', { isSuccess: true, result } as never));
    await flush();

    expect(collected).toEqual([result]);
  });

  it('still forwards non-tool_execute events through the shared handler', async () => {
    // The LCA wrapper must NOT swallow the rest of the event stream — only
    // `tool_execute` is the LCA-irrelevant case. A `stream_chunk` carries
    // text content; the shared handler's optimistic dispatch must still fire.
    const store = createStore();
    const handler = createLcaGatewayEventHandler(() => store, {
      assistantMessageId: 'seed-msg',
      context,
      operationId: 'op-1',
    });

    handler(
      makeEvent('stream_chunk', {
        chunkType: 'text',
        content: 'hello from LCA',
      }),
    );
    await flush();

    expect(store.internal_dispatchMessage).toHaveBeenCalledWith(
      expect.objectContaining({ value: { content: 'hello from LCA' } }),
      expect.any(Object),
    );
  });
});
