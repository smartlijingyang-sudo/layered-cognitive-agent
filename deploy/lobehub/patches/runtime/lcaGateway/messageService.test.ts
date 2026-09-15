// LCA-P1: unit test for the in-memory message adapter.
//
// Copied into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/messageService.test.ts`
// by `lca_runtime_agent_gateway`; run it from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/messageService.test.ts

import type { ConversationContext, UIChatMessage } from '@lobechat/types';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { messageService } from '@/services/message';
import type { ChatStore } from '@/store/chat/store';
import { messageMapKey } from '@/store/chat/utils/messageMapKey';

import { createLcaInMemoryMessagesReader } from './messageService';

const context = {
  agentId: 'agent-1',
  topicId: 'topic-1',
} as ConversationContext;

/** Bucket key the store writes this conversation's raw messages into. */
const keyFor = (topicId: string | null) => messageMapKey({ agentId: 'agent-1', topicId });
const topicKey = keyFor('topic-1');

/**
 * What the LCA stream leaves in the store after three `step_start` boundaries:
 * one assistant row and one `role: 'tool'` row per step, each assistant row
 * already carrying its tool call with `result.content` filled in.
 */
const threeSteps = [
  { content: 'book me a flight', id: 'msg-user', role: 'user' },
  {
    content: 'searching',
    id: 'msg-step-1',
    role: 'assistant',
    tools: [
      {
        function: { arguments: '{"q":"PEK"}', name: 'searchFlights' },
        id: 'call-1',
        result: { content: '3 flights', id: 'call-1' },
        type: 'default',
      },
    ],
  },
  { content: '3 flights', id: 'msg-tool-1', role: 'tool', tool_call_id: 'call-1' },
  {
    content: 'comparing',
    id: 'msg-step-2',
    role: 'assistant',
    tools: [
      {
        function: { arguments: '{"ids":[1,2]}', name: 'compareQuotes' },
        id: 'call-2',
        result: { content: 'cheapest: MU-5101', id: 'call-2' },
        type: 'default',
      },
    ],
  },
  { content: 'cheapest: MU-5101', id: 'msg-tool-2', role: 'tool', tool_call_id: 'call-2' },
  {
    content: 'I booked MU-5101 for you',
    id: 'msg-step-3',
    role: 'assistant',
    tools: [
      {
        function: { arguments: '{"flight":"MU-5101"}', name: 'bookFlight' },
        id: 'call-3',
        result: { content: 'confirmed', id: 'call-3' },
        type: 'default',
      },
    ],
  },
  { content: 'confirmed', id: 'msg-tool-3', role: 'tool', tool_call_id: 'call-3' },
] as unknown as UIChatMessage[];

const createStore = (dbMessagesMap: Record<string, UIChatMessage[]> = {}) =>
  ({
    activeAgentId: 'agent-1',
    activeTopicId: 'topic-1',
    dbMessagesMap,
  }) as unknown as ChatStore;

// The DB is never empty in these tests: it holds the hollow mid-run rows the
// adapter exists to avoid reading, so any DB read shows up as a content
// mismatch on top of the call spy.
const hollowDbRows = [
  { content: '', id: 'msg-step-1', role: 'assistant' },
] as unknown as UIChatMessage[];

describe('createLcaInMemoryMessagesReader', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(messageService, 'getMessages').mockResolvedValue(hollowDbRows);
  });

  it('returns the in-memory three-step snapshot byte-for-byte', async () => {
    const reader = createLcaInMemoryMessagesReader(() => createStore({ [topicKey]: threeSteps }));

    const messages = await reader(context);

    expect(JSON.stringify(messages)).toBe(JSON.stringify(threeSteps));
  });

  it('never reads the message service', async () => {
    const reader = createLcaInMemoryMessagesReader(() => createStore({ [topicKey]: threeSteps }));

    await reader(context);

    expect(messageService.getMessages).not.toHaveBeenCalled();
  });

  it('answers a skipWorks mid-run query with the same snapshot, works included', async () => {
    const works = [{ id: 'wrk-1', type: 'file' }];
    const snapshot = [
      ...threeSteps.slice(0, -1),
      { ...threeSteps.at(-1)!, works },
    ] as unknown as UIChatMessage[];
    const reader = createLcaInMemoryMessagesReader(() => createStore({ [topicKey]: snapshot }));

    const messages = await reader({ ...context, skipWorks: true });

    expect(messages).toStrictEqual(snapshot);
    expect(messages.at(-1)?.works).toStrictEqual(works);
    expect(messageService.getMessages).not.toHaveBeenCalled();
  });

  it('resolves the bucket from the query, not from the active conversation', async () => {
    const background = [
      { content: 'older turn', id: 'msg-bg', role: 'assistant' },
    ] as unknown as UIChatMessage[];
    const store = createStore({
      [keyFor('topic-bg')]: background,
      [topicKey]: threeSteps,
    });
    store.activeTopicId = 'topic-bg';
    const reader = createLcaInMemoryMessagesReader(() => store);

    expect(await reader(context)).toStrictEqual(threeSteps);
  });

  it('mirrors the store fallbacks: no topicId reads the active one, null reads the new one', async () => {
    const newTopic = [
      { content: 'a new topic', id: 'msg-new', role: 'assistant' },
    ] as unknown as UIChatMessage[];
    const reader = createLcaInMemoryMessagesReader(() =>
      createStore({ [keyFor(null)]: newTopic, [topicKey]: threeSteps }),
    );

    const { topicId: _unused, ...noTopicId } = context;

    expect(await reader(noTopicId as ConversationContext)).toStrictEqual(threeSteps);
    expect(await reader({ ...context, topicId: null })).toStrictEqual(newTopic);
  });

  it('returns an empty snapshot for a bucket the store never loaded', async () => {
    const reader = createLcaInMemoryMessagesReader(() => createStore({ [topicKey]: threeSteps }));

    const messages = await reader({ ...context, topicId: 'topic-never-loaded' });

    expect(messages).toStrictEqual([]);
    expect(messageService.getMessages).not.toHaveBeenCalled();
  });
});
