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

import { createLcaInMemoryMessagesReader } from './messageService';

const log = debug('lobe-client:lca-gateway');

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
 */
export const createLcaGatewayEventHandler: typeof createGatewayEventHandler = (get, params) => {
  const handler = createGatewayEventHandler(get, {
    ...params,
    messageService: { getMessages: createLcaInMemoryMessagesReader(get) },
    runtimeType: 'lca-gateway',
  });

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
    handler(event);
  };
};
