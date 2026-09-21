import type { ConversationContext, UIChatMessage } from '@lobechat/types';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { messageService } from '@/services/message';
import type { ChatStore } from '@/store/chat/store';
import { messageMapKey } from '@/store/chat/utils/messageMapKey';

import {
  ensureLcaToolMessages,
  findChildAssistant,
  openLcaAssistantStep,
  persistLcaToolResult,
} from './lcaStepPersist';

const context = {
  agentId: 'agent-1',
  topicId: 'topic-1',
} as ConversationContext;

const topicKey = messageMapKey({ agentId: 'agent-1', topicId: 'topic-1' });

const createStore = () => {
  const dbMessagesMap: Record<string, UIChatMessage[]> = {
    [topicKey]: [
      { content: 'hi', id: 'msg-user', role: 'user' } as unknown as UIChatMessage,
      {
        content: '',
        id: 'asst-1',
        parentId: 'msg-user',
        role: 'assistant',
      } as unknown as UIChatMessage,
    ],
  };

  const store = {
    activeAgentId: 'agent-1',
    activeTopicId: 'topic-1',
    associateMessageWithOperation: vi.fn(),
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
          if (idx >= 0) bucket[idx] = { ...bucket[idx], ...payload.value } as UIChatMessage;
        }
      },
    ),
    internal_toggleToolCallingStreaming: vi.fn(),
  } as unknown as ChatStore;

  return store;
};

describe('lcaStepPersist', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(messageService, 'createMessage').mockResolvedValue({
      id: 'ignored',
      messages: [],
    } as never);
    vi.spyOn(messageService, 'updateToolMessage').mockResolvedValue({ success: true } as never);
    vi.spyOn(messageService, 'updateMessage').mockResolvedValue({ success: true } as never);
  });

  it('reuses an already-created child assistant instead of inserting a duplicate', () => {
    const store = createStore();
    const first = openLcaAssistantStep(store, {
      context,
      operationId: 'op-1',
      parentAssistantId: 'asst-1',
    });
    const again = findChildAssistant(store, context, 'asst-1');
    expect(again?.id).toBe(first.id);
    expect(store.dbMessagesMap[topicKey].filter((m) => m.role === 'assistant')).toHaveLength(2);
  });

  it('opens the next assistant as a child of the previous step and writes it to the message DB', () => {
    const store = createStore();
    const next = openLcaAssistantStep(store, {
      context,
      operationId: 'op-1',
      parentAssistantId: 'asst-1',
    });

    expect(next.id).toBeTruthy();
    expect(next.id).not.toBe('asst-1');
    const created = store.dbMessagesMap[topicKey].find((m) => m.id === next.id);
    expect(created?.role).toBe('assistant');
    expect(created?.parentId).toBe('asst-1');
    expect(messageService.createMessage).toHaveBeenCalledWith(
      expect.objectContaining({ id: next.id, parentId: 'asst-1', role: 'assistant' }),
    );
  });

  it('creates a tool message row for every new tool call so result/state live in the DB', () => {
    const store = createStore();
    const tools = ensureLcaToolMessages(store, {
      assistantId: 'asst-1',
      context,
      operationId: 'op-1',
      toolsCalling: [
        {
          apiName: 'runCommand',
          arguments: '{"command":"ls"}',
          id: 'tc-1',
          identifier: 'lobe-cloud-sandbox',
          type: 'builtin',
        },
      ],
    });

    expect(tools[0]?.result_msg_id).toBeTruthy();
    const toolRow = store.dbMessagesMap[topicKey].find((m) => m.role === 'tool');
    expect(toolRow?.parentId).toBe('asst-1');
    expect(toolRow?.tool_call_id).toBe('tc-1');
    expect(messageService.createMessage).toHaveBeenCalledWith(
      expect.objectContaining({ parentId: 'asst-1', role: 'tool', tool_call_id: 'tc-1' }),
    );
  });

  it('stamps pluginIntervention pending onto tool rows for human-approval calls', () => {
    const store = createStore();
    const tools = ensureLcaToolMessages(store, {
      assistantId: 'asst-1',
      context,
      operationId: 'op-1',
      toolsCalling: [
        {
          apiName: 'askUserQuestion',
          arguments: '{"lca_run_id":"run-1","questions":[]}',
          id: 'tc-ask',
          identifier: 'lobe-user-interaction',
          intervention: { status: 'pending' },
          type: 'builtin',
        },
      ],
    });

    expect(tools[0]?.result_msg_id).toBeTruthy();
    const toolRow = store.dbMessagesMap[topicKey].find((m) => m.id === tools[0]?.result_msg_id);
    expect(toolRow?.pluginIntervention).toEqual({ status: 'pending' });
    expect(messageService.createMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        parentId: 'asst-1',
        role: 'tool',
        tool_call_id: 'tc-ask',
        pluginIntervention: { status: 'pending' },
      }),
    );
  });

  it('stamps pending intervention onto an already-created tool row when the real record follows the placeholder', () => {
    const store = createStore();
    // 占位 tools_calling（无 intervention）先建行
    ensureLcaToolMessages(store, {
      assistantId: 'asst-1',
      context,
      operationId: 'op-1',
      toolsCalling: [
        {
          apiName: 'askUserQuestion',
          arguments: '{"questions":[]}',
          id: 'tc-ask2',
          identifier: 'lobe-user-interaction',
          type: 'builtin',
        },
      ],
    });

    const rowBefore = store.dbMessagesMap[topicKey].find(
      (m) => m.role === 'tool' && m.tool_call_id === 'tc-ask2',
    );
    expect(rowBefore?.pluginIntervention).toBeUndefined();

    // 正式 tools_calling（带 intervention）应补 stamp 到已存在的行
    ensureLcaToolMessages(store, {
      assistantId: 'asst-1',
      context,
      operationId: 'op-1',
      toolsCalling: [
        {
          apiName: 'askUserQuestion',
          arguments: '{"lca_run_id":"run-1","questions":[]}',
          id: 'tc-ask2',
          identifier: 'lobe-user-interaction',
          intervention: { status: 'pending' },
          type: 'builtin',
        },
      ],
    });

    const rowAfter = store.dbMessagesMap[topicKey].find(
      (m) => m.role === 'tool' && m.tool_call_id === 'tc-ask2',
    );
    expect(rowAfter?.pluginIntervention).toEqual({ status: 'pending' });
  });

  it('writes tool_end content and pluginState onto the tool message, not only assistant.tools', async () => {
    const store = createStore();
    const tools = ensureLcaToolMessages(store, {
      assistantId: 'asst-1',
      context,
      operationId: 'op-1',
      toolsCalling: [
        {
          apiName: 'runCommand',
          arguments: '{"command":"ls"}',
          id: 'tc-1',
          identifier: 'lobe-cloud-sandbox',
          type: 'builtin',
        },
      ],
    });
    const toolMessageId = tools[0]?.result_msg_id;
    expect(toolMessageId).toBeTruthy();

    persistLcaToolResult(store, {
      context,
      operationId: 'op-1',
      result: { content: 'ok', state: { stdout: 'ok' } },
      toolCallId: 'tc-1',
    });

    const toolRow = store.dbMessagesMap[topicKey].find((m) => m.id === toolMessageId);
    expect(toolRow?.content).toBe('ok');
    expect(toolRow?.pluginState).toEqual({ stdout: 'ok' });
    expect(messageService.updateToolMessage).toHaveBeenCalledWith(
      toolMessageId,
      expect.objectContaining({ content: 'ok', pluginState: { stdout: 'ok' } }),
      expect.objectContaining({ agentId: 'agent-1', topicId: 'topic-1' }),
    );
  });
});
