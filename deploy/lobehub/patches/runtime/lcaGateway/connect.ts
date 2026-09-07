// LCA-P1: thin wrapper around AgentStreamClient that points at the LCA
// gateway URL. The native connectToGateway lives at
// lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/connect.ts
// — we mirror its factory shape but override the URL so the patched
// front-end dials LCA's WS instead of the legacy /live SSE.

import { AgentStreamClient } from '@lobechat/agent-gateway-client';

import { getLcaGatewayUrl } from './client';

export interface LcaConnectParams {
  /** Server-confirmed run_id from POST /lca-api/runs. */
  operationId: string;
  /** Token from the run receipt's `ws_token` field. */
  token: string;
  /** Whether to buffer events until resume_complete (page-reload reconnect). */
  resumeOnConnect?: boolean;
}

export function lcaConnectToGateway(params: LcaConnectParams): AgentStreamClient {
  const url = getLcaGatewayUrl();
  return new AgentStreamClient({
    gatewayUrl: url,
    operationId: params.operationId,
    resumeOnConnect: params.resumeOnConnect ?? false,
    token: params.token,
  });
}