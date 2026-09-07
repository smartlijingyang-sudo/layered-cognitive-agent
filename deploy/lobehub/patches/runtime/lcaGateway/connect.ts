// LCA-P1: LCA agent-gateway WebSocket factory.
//
// Returns an LcaAgentStreamClient (see LcaAgentStreamClient.ts) wired
// against ADR-0200 §1 server-side surface:
//   <gatewayBase>/v1/runs/<run_id>/ws
//
// Deliberately does NOT delegate to the upstream AgentStreamClient:
// that class hard-codes `<base>/ws?operationId=...` for lobehub's own
// gateway server, which is a different wire path. See
// `LcaAgentStreamClient` file header for the full rationale.

import { LcaAgentStreamClient } from './LcaAgentStreamClient';
import { getLcaGatewayUrl } from './client';

export interface LcaConnectParams {
  /** Server-confirmed run_id from POST /lca-api/runs. */
  operationId: string;
  /** Token from the run receipt's `ws_token` field. */
  token: string;
  /**
   * Accepted for API parity with the upstream connect. Currently a
   * no-op (see LcaAgentStreamClient.ts file header for the resume
   * buffering deferral).
   */
  resumeOnConnect?: boolean;
}

export function lcaConnectToGateway(params: LcaConnectParams): LcaAgentStreamClient {
  return new LcaAgentStreamClient({
    gatewayBase: getLcaGatewayUrl(),
    operationId: params.operationId,
    resumeOnConnect: params.resumeOnConnect,
    token: params.token,
  });
}

export { LcaAgentStreamClient } from './LcaAgentStreamClient';