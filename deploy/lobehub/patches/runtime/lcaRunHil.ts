/**
 * Human-in-the-loop (HIL) coordination for LCA runs (ADR-0100).
 *
 * When live SSE emits ``done.status=awaiting_human``, present the native
 * askUserQuestion intervention card and persist run_id for resume via
 * POST /runs/{id}/answer.
 */

import type { MessageToolCall } from '@lobechat/types';

import type { ChatStore } from '@/store/chat/store';

import { fetchRunSnapshot } from './lcaRunCommand';
import { WIRE } from './lcaWire';

export type HilTurnTool = {
  call: MessageToolCall;
  resultMsgId?: string;
};

export type PresentAskUserCardArgs = {
  agentId?: string;
  assistantId: string;
  currentTurnTools: HilTurnTool[];
  dispatchMessage: (id: string, value: Record<string, unknown>) => void;
  ensureTurn: () => Promise<void>;
  findAskUserTurnTool: () => HilTurnTool | undefined;
  get: () => ChatStore;
  mergeInvocationArgs: (previous: string, state: Record<string, unknown> | undefined) => string;
  operationId: string;
  persistRow: () => Promise<void>;
  publishTurnTools: (streaming: boolean) => void;
  runId: string;
  setLastResultMsgId: (id: string) => void;
  threadId?: string;
  tools: Map<string, HilTurnTool>;
  topicId?: string;
};

export async function presentAskUserCard(args: PresentAskUserCardArgs): Promise<void> {
  const snap = await fetchRunSnapshot(args.runId);
  const questions = Array.isArray(snap.approval_request?.questions)
    ? snap.approval_request.questions
    : [];
  if (!questions.length) return;

  await args.ensureTurn();
  const pair = WIRE.askUserQuestion;
  const existing = args.findAskUserTurnTool();
  if (existing?.resultMsgId && pair) {
    existing.call.function.arguments = args.mergeInvocationArgs(existing.call.function.arguments, {
      lca_run_id: args.runId,
      questions,
    });
    args.dispatchMessage(existing.resultMsgId, {
      plugin: {
        apiName: pair[1],
        arguments: existing.call.function.arguments,
        identifier: pair[0],
        id: existing.call.id,
        type: 'builtin',
      },
      pluginIntervention: { status: 'pending' },
    });
    await args.get().optimisticUpdatePluginState(
      existing.resultMsgId,
      { lca: { run_id: args.runId, status: 'waiting_input' } },
      { operationId: args.operationId },
    );
    args.publishTurnTools(false);
    await args.persistRow();
    return;
  }

  const callId = `ask_${args.runId}`;
  const call: MessageToolCall = {
    function: {
      arguments: JSON.stringify({ lca_run_id: args.runId, questions }),
      name: 'lobe-user-interaction____askUserQuestion',
    },
    id: callId,
    type: 'function',
  };
  const rec: HilTurnTool = { call };
  args.tools.set(callId, rec);
  args.currentTurnTools.push(rec);
  const created = await args.get().optimisticCreateMessage(
    {
      content: '',
      parentId: args.assistantId,
      plugin: {
        apiName: 'askUserQuestion',
        arguments: JSON.stringify({ lca_run_id: args.runId, questions }),
        identifier: 'lobe-user-interaction',
        id: callId,
        type: 'builtin',
      },
      pluginIntervention: { status: 'pending' },
      role: 'tool',
      tool_call_id: callId,
      topicId: args.topicId,
      ...(args.agentId ? { agentId: args.agentId } : {}),
      ...(args.threadId ? { threadId: args.threadId } : {}),
    },
    { operationId: args.operationId },
  );
  rec.resultMsgId = created?.id;
  if (created?.id) {
    args.setLastResultMsgId(created.id);
    await args.get().optimisticUpdatePluginState(
      created.id,
      { lca: { run_id: args.runId, status: 'waiting_input' } },
      { operationId: args.operationId },
    );
  }
  args.publishTurnTools(false);
  await args.persistRow();
}
