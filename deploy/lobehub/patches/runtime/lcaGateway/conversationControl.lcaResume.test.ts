import { RequestTrigger } from '@lobechat/types';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { messageService } from '@/services/message';

import { useChatStore } from '../../../../store';
import { messageMapKey } from '../../../../utils/messageMapKey';
import { createMockMessage } from './fixtures';
import { resetTestEnvironment } from './helpers';

// Keep zustand mock as it's needed globally
vi.mock('zustand/traditional');

// Mock the tRPC client & agentRuntimeService so the import chain doesn't pull
// server-only code into the test env.
vi.mock('@/libs/trpc/client', () => ({
  lambdaClient: {
    aiAgent: {
      processHumanIntervention: { mutate: vi.fn().mockResolvedValue({ success: true }) },
      submitHeteroIntervention: { mutate: vi.fn().mockResolvedValue({ success: true }) },
    },
  },
}));

vi.mock('@/services/agentRuntime', () => ({
  agentRuntimeService: {
    handleHumanIntervention: vi.fn().mockResolvedValue({ success: true }),
  },
}));

vi.mock('@/utils/localStorage', () => {
  class AsyncLocalStorage<State> {
    getFromLocalStorageSync(): State {
      return {} as State;
    }

    async getFromLocalStorage(): Promise<State> {
      return {} as State;
    }

    async saveToLocalStorage(): Promise<void> {
      return undefined;
    }
  }

  return { AsyncLocalStorage };
});

// Mock the LCA resume helper so submitToolInteraction's dynamic import
// resolves without touching the gateway transport.
const { lcaResumeGatewayRun } = vi.hoisted(() => ({
  lcaResumeGatewayRun: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('@/store/chat/agents/transports/lcaGateway/executeGatewayRun', () => ({
  lcaResumeGatewayRun,
}));

describe('submitToolInteraction LCA resume', () => {
  beforeEach(() => {
    resetTestEnvironment();
    useChatStore.setState({
      updateTopicStatus: vi.fn().mockResolvedValue(undefined),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps streamed assistant reasoning across an LCA askUserQuestion resume', async () => {
    const { result } = renderHook(() => useChatStore());

    const agentId = 'lca-agent';
    const topicId = 'lca-topic';
    const chatKey = messageMapKey({ agentId, topicId });

    const userMessage = createMockMessage({
      id: 'user-msg',
      metadata: { trigger: RequestTrigger.Chat },
      role: 'user',
    });
    const assistantMessage = {
      ...createMockMessage({
        id: 'assistant-msg',
        parentId: userMessage.id,
        role: 'assistant',
      }),
      reasoning: { content: '用户请求连接本机电脑' },
      tools: [
        {
          apiName: 'askUserQuestion',
          arguments: '{}',
          id: 'call_ask',
          identifier: 'lobe-user-interaction',
          type: 'builtin',
        },
      ],
    } as any;
    const toolMessage = {
      ...createMockMessage({
        groupId: 'group-1',
        id: 'tool-msg-1',
        parentId: assistantMessage.id,
        plugin: {
          apiName: 'askUserQuestion',
          arguments: '{}',
          identifier: 'lobe-user-interaction',
          type: 'default',
        },
        role: 'tool',
      }),
      tool_call_id: 'call_ask',
    } as any;

    act(() => {
      useChatStore.setState({
        activeAgentId: agentId,
        activeTopicId: topicId,
        activeThreadId: undefined,
        dbMessagesMap: { [chatKey]: [userMessage, assistantMessage, toolMessage] },
        messagesMap: { [chatKey]: [userMessage, assistantMessage, toolMessage] },
      });
    });

    // Mid-run the DB is hollow: an update echo returns the assistant row
    // WITHOUT reasoning. Before the fix, submitToolInteraction's core
    // optimistic updates replaced the store with this echo, clobbering the
    // streamed reasoning.
    const hollowAssistant = { ...assistantMessage, reasoning: undefined };
    vi.spyOn(messageService, 'updateMessagePlugin').mockResolvedValue({
      success: true,
      messages: [userMessage, hollowAssistant, toolMessage],
    } as never);
    vi.spyOn(messageService, 'updateMessage').mockResolvedValue({
      success: true,
      messages: [userMessage, hollowAssistant, toolMessage],
    } as never);

    await act(async () => {
      await result.current.submitToolInteraction(
        'tool-msg-1',
        { answer: '控制本机' },
        undefined,
        {
          lcaRunId: 'run-lca-1',
          skipResume: true,
          toolResultContent: '控制我的本机电脑 读写文件',
        },
      );
    });

    const stored = useChatStore.getState().dbMessagesMap[chatKey];
    const assistant = stored.find((m) => m.id === 'assistant-msg');
    expect(assistant?.reasoning?.content).toContain('用户请求连接本机电脑');
    expect(lcaResumeGatewayRun).toHaveBeenCalledWith(
      expect.any(Function),
      expect.objectContaining({ runId: 'run-lca-1' }),
    );

    // The LCA skipResume branch mirrors the native gateway resume: after the
    // resume op succeeds, the topic returns to 'active' so the intervention
    // card disappears instead of staying parked at waitingForHuman.
    const updateTopicStatus = useChatStore.getState().updateTopicStatus as ReturnType<
      typeof vi.fn
    >;
    expect(updateTopicStatus).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'active', topicId }),
    );
  });
});
