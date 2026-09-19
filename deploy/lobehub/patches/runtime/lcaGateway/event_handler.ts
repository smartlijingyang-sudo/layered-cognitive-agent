// LCA-P1: LCA gateway event handler factory.
//
// The native handler at
// `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler.ts`
// is the canonical AgentStreamEvent consumer. The LCA transport reuses it
// with two overrides:
//   - `runtimeType: 'lca-gateway'` so the shared handler skips mid-stream
//     DB refetches (LCA persists assistant rows only on turn seal, so a
//     mid-run DB read would clobber content the WS stream already rendered).
//   - `messageService: { getMessages: createLcaInMemoryMessagesReader(get) }`
//     so any non-skipped refetch reconciles against `dbMessagesMap` directly
//     — the same surface `dbMessageSelectors.getDbMessageById` walks —
//     instead of the DB.
//
// `tool_execute` filter:
// The shared handler's `case 'tool_execute':` forwards the payload to
// `internal_executeClientTool`, the client-side tool runtime used by the
// native hetero path (Claude Code / Codex adapters that must execute tools
// locally). LCA's server-side runtime (lobe-cloud-sandbox) executes tools
// itself and never emits `tool_execute` on the wire — see
// `lca/application/runtime/coordinator/event_translator.py` (no `tool_execute`
// handler) and `lca/contracts/transport/agent_stream_event.py:188` (schema
// declared but unused). Forwarding a `tool_execute` event through the shared
// handler would invoke `internal_executeClientTool` and try to reply on a
// `gatewayConnections` entry that the LCA transport does not register,
// failing open into a phantom `tool_result` that the server never asked for.
//
// We therefore intercept `tool_execute` here, log a single debug line, and
// drop the event before it reaches the shared switch. The shared case stays
// intact for native (where the event is real and the path is needed).

import type { AgentStreamEvent } from '@lobechat/agent-gateway-client';
import debug from 'debug';

import { createGatewayEventHandler } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler';

import type { LcaDeliverables } from './deliverables';
import {
  ensureLcaToolMessages,
  findChildAssistant,
  openLcaAssistantStep,
  persistLcaToolResult,
} from './lcaStepPersist';
import { createLcaInMemoryMessagesReader } from './messageService';

const log = debug('lobe-client:lca-gateway');

const noopDeliverables: LcaDeliverables = {
  collectClosure: () => undefined,
  files: () => [],
  lists: () => ({ fileList: [], imageList: [] }),
};

/**
 * Build the LCA gateway event handler. Delegates to the shared native
 * handler factory and threads the LCA in-memory reader through
 * `messageService.getMessages`, so mid-run reads return the live store
 * snapshot instead of hollow DB rows.
 *
 * The returned handler is a thin wrapper around the shared native handler:
 * it drops `tool_execute` events before they reach the shared switch
 * (the LCA runtime never emits them — see file header). The shared case
 * remains intact for the native hetero path.
 *
 * `deliverables` optionally folds the artifact closure carried by
 * ``agent_runtime_end`` so the caller can attach them to the answer row when
 * the run ends. The closure is synthesized from the backend workspace ledger
 * and is tool-agnostic (executeCode / runCommand / exportFile all land here).
 */
export const createLcaGatewayEventHandler = (
  get: Parameters<typeof createGatewayEventHandler>[0],
  params: Parameters<typeof createGatewayEventHandler>[1] & { resuming?: boolean },
  deliverables: LcaDeliverables = noopDeliverables,
) => {
  const handler = createGatewayEventHandler(get, {
    ...params,
    messageService: { getMessages: createLcaInMemoryMessagesReader(get) },
    runtimeType: 'lca-gateway',
  });

  let currentAssistantId = params.assistantMessageId;
  // A resume op's first stream_start opens a CHILD assistant step under the
  // previous step's assistant (correct for a resumed run), rather than being
  // treated as the first step of a fresh run.
  let llmStepOpened = params.resuming ?? false;

  return (event: AgentStreamEvent) => {
    if (event.type === 'tool_execute') {
      // LCA never emits `tool_execute` on the wire; if one arrives it is
      // either a misroute from another transport or a contract drift. Drop
      // it explicitly so a future developer (or a regression that wires a
      // new client-executable tool) sees the intent in the log rather than
      // silently dispatching `internal_executeClientTool` against a
      // gatewayConnections entry the LCA transport never registered.
      log(
        'lca-gateway does not emit tool_execute; ignoring toolCallId=%s',
        (event.data as { toolCallId?: string } | undefined)?.toolCallId,
      );
      return;
    }

    let nextEvent = event;
    const store = get();

    if (event.type === 'stream_start') {
      const incomingId = (event.data as { assistantMessage?: { id?: string } } | undefined)
        ?.assistantMessage?.id;
      if (llmStepOpened && currentAssistantId) {
        const existing = findChildAssistant(store, params.context, currentAssistantId);
        const stepId = existing?.id
          ? existing.id
          : openLcaAssistantStep(store, {
              context: params.context,
              operationId: params.operationId,
              parentAssistantId: currentAssistantId,
            }).id;
        currentAssistantId = stepId;
        nextEvent = {
          ...event,
          data: {
            ...(event.data as object),
            assistantMessage: {
              ...((event.data as { assistantMessage?: object } | undefined)?.assistantMessage ??
                {}),
              id: stepId,
            },
          },
        } as AgentStreamEvent;
      } else {
        llmStepOpened = true;
        if (incomingId) currentAssistantId = incomingId;
      }
    }

    if (
      event.type === 'stream_chunk' &&
      (event.data as { chunkType?: string } | undefined)?.chunkType === 'tools_calling'
    ) {
      const data = event.data as { toolsCalling?: Array<Record<string, unknown>> };
      if (currentAssistantId && Array.isArray(data.toolsCalling)) {
        const toolsCalling = ensureLcaToolMessages(store, {
          assistantId: currentAssistantId,
          context: params.context,
          operationId: params.operationId,
          toolsCalling: data.toolsCalling,
        });
        nextEvent = {
          ...event,
          data: { ...data, toolsCalling },
        } as AgentStreamEvent;
      }
    }

    if (event.type === 'tool_end') {
      const data = event.data as {
        payload?: { toolCalling?: { id?: string } };
        result?: { content?: unknown; error?: unknown; state?: unknown };
        toolCallId?: string;
      };
      const toolCallId = data.payload?.toolCalling?.id || data.toolCallId;
      if (toolCallId) {
        persistLcaToolResult(store, {
          context: params.context,
          operationId: params.operationId,
          result: data.result,
          toolCallId,
        });
      }
    }

    if (event.type === 'agent_runtime_end') {
      const data = event.data as {
        artifactClosure?: unknown;
        reason?: string;
      };
      if (data.artifactClosure !== undefined) {
        deliverables.collectClosure(data.artifactClosure);
      }
    }

    handler(nextEvent);
  };
};
