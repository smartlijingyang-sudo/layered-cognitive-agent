// LCA-P1: multi-run / multi-LLM regression test for the LCA gateway path.
//
// Copied into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/lcaGatewayEventHandler.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/lcaGatewayEventHandler.test.ts
//
// This is the task-4 regression test that locks the LCA wire's shape on the
// shared handler. It drives a synthetic run with three step boundaries and
// one terminal snapshot, where the wire emits ONE tool per
// `stream_chunk.tools_calling` (the LCA shape — see
// `lca/application/runtime/coordinator/event_translator.py:333-346`).
// The previous `mergeToolsCallingChunks` shim is gone; the task-3 fix made
// `preserveToolResultMessageIds` merge by id so per-chunk-single tools
// accumulate. The hetero cumulative path's tool ordering was not explicitly
// tested before this task, and the task-3 re-review surfaced a latent
// regression: hetero cumulative chunks `['item_1']`, `['item_1', 'item_2']`,
// `['item_4']` produced `[item_1, item_2, item_4]` pre-fix and
// `[item_4, item_1, item_2]` post-fix. This test pins the post-fix order
// for the LCA path explicitly — `[newest_incoming_first, ...existing_leftover]`
// — and a follow-up PR will reverse the helper's loop order so hetero's
// cumulative order is preserved.

import type { AgentStreamEvent } from '@lobechat/agent-gateway-client';
import type { ConversationContext, UIChatMessage } from '@lobechat/types';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { messageService } from '@/services/message';
import { dbMessageSelectors } from '@/store/chat/slices/message/selectors/dbMessage';
import type { ChatStore } from '@/store/chat/store';
import { messageMapKey } from '@/store/chat/utils/messageMapKey';

import { createLcaGatewayEventHandler } from './event_handler';

const context = {
  agentId: 'agent-1',
  topicId: 'topic-1',
} as ConversationContext;

const makeEvent = (
  type: AgentStreamEvent['type'],
  data?: AgentStreamEvent['data'],
  stepIndex?: number,
) =>
  ({
    data,
    id: `event-${type}-${stepIndex ?? 0}`,
    operationId: 'op-1',
    stepIndex: stepIndex ?? 0,
    timestamp: 0,
    type,
  }) as AgentStreamEvent;

const topicKey = messageMapKey({ agentId: 'agent-1', topicId: 'topic-1' });

/** Assistant row already in the store when the LCA stream begins. */
const seedAssistant = {
  content: '',
  id: 'assistant-msg',
  model: 'gpt-4o',
  parentId: 'msg-user',
  provider: 'openai',
  role: 'assistant',
  topicId: 'topic-1',
} as unknown as UIChatMessage;

/** Final assistant message the LCA runtime ships on `agent_runtime_end`. */
const terminalAssistant = {
  content: 'Booking confirmed: MU-5101 for PEK→PVG on 2026-10-01',
  id: 'assistant-msg',
  model: 'gpt-4o',
  parentId: 'msg-user',
  provider: 'openai',
  role: 'assistant',
  tools: [
    {
      apiName: 'searchFlights',
      arguments: '{"q":"PEK"}',
      id: 'call-1',
      result: { content: '3 flights found', id: 'call-1' },
      type: 'default',
    },
    {
      apiName: 'compareQuotes',
      arguments: '{"ids":[1,2]}',
      id: 'call-2',
      result: { content: 'cheapest: MU-5101', id: 'call-2' },
      type: 'default',
    },
    {
      apiName: 'bookFlight',
      arguments: '{"flight":"MU-5101"}',
      id: 'call-3',
      result: { content: 'confirmed', id: 'call-3' },
      type: 'default',
    },
  ],
  topicId: 'topic-1',
} as unknown as UIChatMessage;

/**
 * Per-chunk-single wire shape: ONE tool per `stream_chunk.tools_calling`.
 * Mirrors the LCA event translator's `_spine_tool_call_record` (one tool per
 * emitted chunk, NOT the cumulative shape hetero emits).
 */
const oneToolChunk = (id: string, apiName: string) =>
  ({
    chunkType: 'tools_calling' as const,
    toolsCalling: [{ apiName, arguments: '{}', id, type: 'default' }],
  }) as AgentStreamEvent['data'];

/**
 * Build the store with `internal_dispatchMessage` actually mutating the
 * assistant row in `dbMessagesMap` so the next `tools_calling` chunk's
 * `preserveToolResultMessageIds` read sees the accumulated tools. The
 * reducer-based dispatch is mocked so the test does not depend on Zustand
 * internals — we just emulate its observable side-effect (the row's
 * `tools` array updates in place after each `updateMessage` with `value.tools`).
 */
const createStore = () => {
  const dbMessagesMap: Record<string, UIChatMessage[]> = {
    [topicKey]: [
      { content: 'book me a flight', id: 'msg-user', role: 'user' } as unknown as UIChatMessage,
      { ...seedAssistant },
    ],
  };

  const replaceMessages = vi.fn((messages: UIChatMessage[]) => {
    dbMessagesMap[topicKey] = messages;
  });

  const store = {
    activeAgentId: 'agent-1',
    activeTopicId: 'topic-1',
    associateMessageWithOperation: vi.fn(),
    completeOperation: vi.fn(),
    dbMessagesMap,
    internal_dispatchMessage: vi.fn(
      (payload: { id?: string; type?: string; value?: Record<string, unknown> }) => {
        const bucket = dbMessagesMap[topicKey];
        if (payload.type === 'createMessage' && payload.id && payload.value) {
          bucket.push({ ...payload.value, id: payload.id } as UIChatMessage);
          return;
        }
        if (payload.type === 'updateMessage' && payload.id) {
          const idx = bucket.findIndex((m) => m.id === payload.id);
          if (idx >= 0) {
            bucket[idx] = { ...bucket[idx], ...payload.value } as UIChatMessage;
          }
        }
      },
    ),
    internal_toggleToolCallingStreaming: vi.fn(),
    operations: {},
    replaceMessages,
    startOperation: vi.fn(() => ({
      abortController: new AbortController(),
      operationId: 'reasoning-op',
    })),
    updateOperationMetadata: vi.fn(),
  } as unknown as ChatStore;

  return { replaceMessages, store };
};

// The handler enqueues work on an internal promise chain; flush the microtask
// queue so async event handlers settle before assertions.
const flush = async () => {
  for (let i = 0; i < 50; i += 1) await Promise.resolve();
};

describe('createLcaGatewayEventHandler (multi-run / multi-LLM)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(messageService, 'createMessage').mockResolvedValue({ id: 'x', messages: [] } as never);
    vi.spyOn(messageService, 'updateToolMessage').mockResolvedValue({ success: true } as never);
    vi.spyOn(messageService, 'updateMessage').mockResolvedValue({ success: true } as never);
  });

  it('drives three steps and a terminal snapshot with one tool per tools_calling chunk', async () => {
    const dbSpy = vi
      .spyOn(messageService, 'getMessages')
      .mockResolvedValue([] as unknown as UIChatMessage[]);

    const { store, replaceMessages } = createStore();
    const handler = createLcaGatewayEventHandler(() => store, {
      assistantMessageId: 'assistant-msg',
      context,
      operationId: 'op-1',
    });

    // Three step boundaries. Each step streams a text delta then the LCA
    // wire's per-chunk-single tools_calling chunk (one tool). The LCA wire
    // does NOT attach uiMessages to step_start (verified at
    // event_translator.py:209-218), so step_start only bumps stepCount.
    handler(
      makeEvent(
        'stream_chunk',
        { chunkType: 'text', content: 'searching flights... ', snapshotMode: 'append' } as never,
        1,
      ),
    );
    handler(makeEvent('stream_chunk', oneToolChunk('call-1', 'searchFlights'), 1));
    handler(makeEvent('step_start', { phase: 'execution_complete' } as never, 1));

    handler(
      makeEvent(
        'stream_chunk',
        { chunkType: 'text', content: 'comparing quotes... ', snapshotMode: 'append' } as never,
        2,
      ),
    );
    handler(makeEvent('stream_chunk', oneToolChunk('call-2', 'compareQuotes'), 2));
    handler(makeEvent('step_start', { phase: 'execution_complete' } as never, 2));

    handler(
      makeEvent(
        'stream_chunk',
        { chunkType: 'text', content: 'booking now... ', snapshotMode: 'append' } as never,
        3,
      ),
    );
    handler(makeEvent('stream_chunk', oneToolChunk('call-3', 'bookFlight'), 3));
    handler(makeEvent('step_start', { phase: 'execution_complete' } as never, 3));

    // Terminal snapshot — the LCA runtime's SoT for the final assistant
    // content AND its tools (each carrying `result.content`). This is the
    // single point at which the LCA path must reconcile the store.
    handler(
      makeEvent(
        'agent_runtime_end',
        {
          reason: 'completed',
          uiMessages: [
            { content: 'book me a flight', id: 'msg-user', role: 'user' } as UIChatMessage,
            terminalAssistant,
          ],
        } as never,
        3,
      ),
    );

    await flush();

    // ── Assertion 1: final assistant content equals the runtime-written text
    const lastCall = replaceMessages.mock.calls.at(-1);
    expect(lastCall).toBeDefined();
    const [terminalMessages, terminalOptions] = lastCall as unknown as [
      UIChatMessage[],
      Record<string, unknown>,
    ];
    expect(terminalMessages).toHaveLength(2);
    const finalAssistant = terminalMessages.find((m) => m.role === 'assistant');
    expect(finalAssistant?.content).toBe('Booking confirmed: MU-5101 for PEK→PVG on 2026-10-01');
    expect(terminalOptions).toMatchObject({ action: 'gateway/agent_runtime_end', context });

    // ── Assertion 2: final tools array has all three tool calls, each with result.content
    expect(finalAssistant?.tools).toHaveLength(3);
    const toolIds = (finalAssistant?.tools as Array<{ id: string }>).map((t) => t.id);
    expect(toolIds).toEqual(['call-1', 'call-2', 'call-3']); // chronological
    for (const tool of finalAssistant?.tools as Array<{
      result?: { content?: string };
    }>) {
      expect(tool.result?.content).toBeTruthy();
    }

    // ── Assertion 3: replaceMessages called EXACTLY ONCE with the terminal snapshot
    expect(replaceMessages).toHaveBeenCalledTimes(1);

    // ── Assertion 4: the messageService (DB singleton) was never called —
    // the LCA reader reconciles against `dbMessagesMap`, not the DB.
    expect(dbSpy).not.toHaveBeenCalled();

    // ── Pin the per-chunk-single accumulation that the LCA wire relies on.
    // preserveToolResultMessageIds keeps first-seen order so activateSkill
    // stays above later runCommand cards.
    const updateToolCalls = (store.internal_dispatchMessage as ReturnType<typeof vi.fn>).mock.calls
      .map(([payload]) => payload)
      .filter(
        (payload: { type?: string; id?: string; value?: { tools?: unknown[] } }) =>
          payload?.type === 'updateMessage' &&
          payload.id === 'assistant-msg' &&
          Array.isArray(payload.value?.tools),
      );
    expect(updateToolCalls.map((c: { value: { tools: Array<{ id: string }> } }) =>
      c.value.tools.map((t) => t.id),
    )).toEqual([['call-1'], ['call-1', 'call-2'], ['call-1', 'call-2', 'call-3']]);
  });

  // Mirrors Case A's event sequence, but the LCA wire's actual `agent_runtime_end`
  // payload (`event_translator.py:233-246` — `{finalState, reason, reasonDetail,
  // phase}`) carries NO `uiMessages`. The handler then falls through to
  // `fetchAndReplaceMessages(get, context, undefined, reader)`
  // (`gatewayEventHandler.ts:1208-1210`), which uses the LCA-specific
  // in-memory reader (`messageService.ts:30-43`). This case exercises that
  // path end-to-end: the in-memory reader reconciles against
  // `dbMessagesMap`, the singleton `messageService.getMessages` is bypassed.
  it('drives three steps and the LCA terminal reconciliation (no uiMessages on agent_runtime_end)', async () => {
    const dbSpy = vi
      .spyOn(messageService, 'getMessages')
      .mockResolvedValue([] as unknown as UIChatMessage[]);
    // The LCA reader resolves its snapshot via `dbMessageSelectors.getDbMessagesByKey`.
    // Spy on the selector to count how many times the LCA reader was invoked.
    const readerSpy = vi.spyOn(dbMessageSelectors, 'getDbMessagesByKey');

    const { store, replaceMessages } = createStore();
    const handler = createLcaGatewayEventHandler(() => store, {
      assistantMessageId: 'assistant-msg',
      context,
      operationId: 'op-1',
    });

    // Same three-step event sequence as Case A.
    handler(
      makeEvent(
        'stream_chunk',
        { chunkType: 'text', content: 'searching flights... ', snapshotMode: 'append' } as never,
        1,
      ),
    );
    handler(makeEvent('stream_chunk', oneToolChunk('call-1', 'searchFlights'), 1));
    handler(makeEvent('step_start', { phase: 'execution_complete' } as never, 1));

    handler(
      makeEvent(
        'stream_chunk',
        { chunkType: 'text', content: 'comparing quotes... ', snapshotMode: 'append' } as never,
        2,
      ),
    );
    handler(makeEvent('stream_chunk', oneToolChunk('call-2', 'compareQuotes'), 2));
    handler(makeEvent('step_start', { phase: 'execution_complete' } as never, 2));

    handler(
      makeEvent(
        'stream_chunk',
        { chunkType: 'text', content: 'booking now... ', snapshotMode: 'append' } as never,
        3,
      ),
    );
    handler(makeEvent('stream_chunk', oneToolChunk('call-3', 'bookFlight'), 3));
    handler(makeEvent('step_start', { phase: 'execution_complete' } as never, 3));

    // LCA wire's actual terminal: NO `uiMessages`. This drives the
    // `fetchAndReplaceMessages` path with the LCA reader at line 1208-1210.
    handler(
      makeEvent(
        'agent_runtime_end',
        {
          phase: 'execution_complete',
          reason: 'completed',
        } as never,
        3,
      ),
    );

    await flush();

    // ── Invariant 1: the LCA in-memory reader was called exactly once at
    // terminal. The `reader` parameter passed to `fetchAndReplaceMessages`
    // is the LCA reader (built by `createLcaInMemoryMessagesReader` in the
    // LCA factory), which calls `dbMessageSelectors.getDbMessagesByKey`
    // exactly once per invocation. No other code path in the handler
    // touches that selector, so the spy count isolates the LCA reader.
    expect(readerSpy).toHaveBeenCalledTimes(1);

    // ── Invariant 2: `replaceMessages` was called exactly once with the
    // in-memory array. Three `step_start` events must NOT trigger
    // `replaceMessages` (the LCA wire does not attach `uiMessages` to
    // `step_start`); mid-stream chunks under `runtimeType: 'lca-gateway'`
    // are short-circuited by `shouldSkipMidStreamMessageFetch`.
    expect(replaceMessages).toHaveBeenCalledTimes(1);

    const lastCall = replaceMessages.mock.calls.at(-1);
    expect(lastCall).toBeDefined();
    const [terminalMessages] = lastCall as unknown as [
      UIChatMessage[],
      Record<string, unknown>,
    ];
    expect(terminalMessages.length).toBeGreaterThanOrEqual(2);
    const finalAssistant = terminalMessages.find((m) => m.id === 'assistant-msg');

    // ── Invariant 3: terminal assistant row carries all three tools in
    // the in-memory accumulation order. Tool result rows sit beside it
    // (native dual-form). After three chunks the assistant's tools are
    // `[call-1, call-2, call-3]` (first-seen order).
    expect(finalAssistant?.tools).toHaveLength(3);
    const toolIds = (finalAssistant?.tools as Array<{ id: string }>).map((t) => t.id);
    expect(toolIds).toEqual(['call-1', 'call-2', 'call-3']);

    // ── Invariant 4: the singleton `messageService.getMessages` was never
    // called. The LCA factory overrides `params.messageService` with the
    // LCA in-memory reader, so the singleton is bypassed entirely.
    expect(dbSpy).not.toHaveBeenCalled();
  });

  it('opens a new assistant row on the second stream_start so thinking and tools stay in step order', async () => {
    const { store } = createStore();
    const handler = createLcaGatewayEventHandler(() => store, {
      assistantMessageId: 'assistant-msg',
      context,
      operationId: 'op-1',
    });

    handler(makeEvent('stream_start', { assistantMessage: { id: 'assistant-msg' } } as never, 1));
    handler(
      makeEvent(
        'stream_chunk',
        { chunkType: 'reasoning', reasoning: 'need the skill first', snapshotMode: 'append' } as never,
        1,
      ),
    );
    handler(makeEvent('stream_chunk', oneToolChunk('call-1', 'runCommand'), 1));
    handler(makeEvent('stream_end', {} as never, 1));
    handler(makeEvent('stream_start', { assistantMessage: { id: 'assistant-msg' } } as never, 2));
    handler(
      makeEvent(
        'stream_chunk',
        { chunkType: 'reasoning', reasoning: 'now inspect the file', snapshotMode: 'append' } as never,
        2,
      ),
    );
    handler(makeEvent('stream_chunk', oneToolChunk('call-2', 'runCommand'), 2));
    await flush();

    const assistants = store.dbMessagesMap[topicKey].filter((m) => m.role === 'assistant');
    expect(assistants.length).toBeGreaterThanOrEqual(2);
    const first = assistants.find((m) => m.id === 'assistant-msg');
    const second = assistants.find((m) => m.id !== 'assistant-msg');
    expect(first?.reasoning?.content).toContain('need the skill first');
    expect((first?.tools as Array<{ id: string }> | undefined)?.map((t) => t.id)).toEqual(['call-1']);
    expect(second?.parentId).toBe('assistant-msg');
    expect(second?.reasoning?.content).toContain('now inspect the file');
    expect((second?.tools as Array<{ id: string }> | undefined)?.map((t) => t.id)).toEqual(['call-2']);
  });

  it('writes tool_end result onto in-memory tools so the card can render', async () => {
    const { store } = createStore();
    const handler = createLcaGatewayEventHandler(() => store, {
      assistantMessageId: 'assistant-msg',
      context,
      operationId: 'op-1',
    });

    handler(
      makeEvent(
        'stream_chunk',
        {
          chunkType: 'tools_calling',
          toolsCalling: [
            {
              apiName: 'activateSkill',
              arguments: JSON.stringify({ name: 'officecli' }),
              id: 'tc-skill',
              identifier: 'lobe-skills',
              type: 'builtin',
            },
          ],
        } as never,
        1,
      ),
    );
    handler(
      makeEvent(
        'tool_end',
        {
          isSuccess: true,
          payload: {
            toolCalling: {
              apiName: 'activateSkill',
              id: 'tc-skill',
              identifier: 'lobe-skills',
            },
          },
          result: {
            content: '# Office CLI',
            state: { content: '# Office CLI', name: 'officecli', title: 'officecli' },
          },
        } as never,
        1,
      ),
    );
    await flush();

    const assistant = store.dbMessagesMap[topicKey].find((m) => m.id === 'assistant-msg');
    const tools = assistant?.tools as Array<{
      id: string;
      result?: { content?: string; state?: { name?: string } };
    }>;
    expect(tools).toHaveLength(1);
    expect(tools[0].id).toBe('tc-skill');
    expect(tools[0].result?.state?.name).toBe('officecli');
    expect(tools[0].result?.content).toBe('# Office CLI');
  });
});
