// LCA-P1: P1 front-end WS gateway client — type definitions.
//
// Mirrors lca/contracts/transport/agent_stream_event.py +
// gateway_messages.py. These are the wire shapes the LcaAgentGateway
// server (Task 8) emits on /v1/runs/{run_id}/ws. The AgentStreamClient
// in @lobechat/agent-gateway-client consumes the same wire types from
// src/types.ts; the re-export below keeps the LCA type surface
// independent so server-side type drift fails at the patch boundary.

import type {
  AgentStreamClientEvents,
  AgentStreamEvent,
  ConnectionStatus,
} from '@lobechat/agent-gateway-client';

import type { LcaAgentStreamClient as LcaAgentStreamClientImpl } from './LcaAgentStreamClient';
import type { LcaAgentStreamClientOptions } from './LcaAgentStreamClient';

export interface LcaRunReceipt {
  run_id: string;
  trace_id: string;
  agent: { id: string; name: string };
  ws_token: string;
}

export interface LcaRunningOperation {
  run_id: string;
  topic_id: string;
  agent_id: string;
  assistant_message_id: string | null;
  scope: string;
  created_at: string;
}

export interface LcaConnectParams {
  operationId: string;
  token: string;
  resumeOnConnect?: boolean;
}

/**
 * The LCA WS client. Public shape is compatible with the upstream
 * AgentStreamClient so createLcaGatewayEventHandler (which is the
 * re-exported upstream handler) keeps working unchanged. See
 * LcaAgentStreamClient.ts for the full rationale.
 */
export type LcaAgentStreamClient = LcaAgentStreamClientImpl;
export type { LcaAgentStreamClientOptions };
export type { AgentStreamClientEvents, AgentStreamEvent, ConnectionStatus };