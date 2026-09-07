// LCA-P1: cross-refresh reconnect.
//
// Reads the running LCA operation for a topic from
// `GET /lca-api/topics/{topicId}/running-op` (plain HTTP), returns
// the operationId + ws_token pair so the caller can re-open the WS.
// Mirrors the legacy useGatewayReconnect shape (a SWR fetcher that
// returns the running op for a topic) but swaps the data source.

import type { LcaRunningOperation } from './types';

function bearer(): string {
  const envToken =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env
          ?.NEXT_PUBLIC_LCA_TOKEN
      : undefined;
  return envToken && envToken.length > 0 ? envToken : 'lca-local';
}

export interface LcaReconnectHandle {
  operationId: string;
  token: string;
}

export async function lcaReconnectToGatewayOperation(
  topicId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<LcaReconnectHandle | null> {
  const resp = await fetchImpl(
    `/lca-api/topics/${encodeURIComponent(topicId)}/running-op`,
    {
      headers: { Authorization: `Bearer ${bearer()}` },
    },
  );
  if (!resp.ok) return null;
  const body = (await resp.json()) as {
    running_operation: LcaRunningOperation | null;
  };
  if (!body.running_operation) return null;
  const op = body.running_operation;
  // The running-op table does not carry ws_token (PR-3 deferred). The
  // caller must call refresh_ws_token to mint a fresh one before
  // opening the WS; for now we return an empty token and the caller
  // is expected to handle the refresh.
  return { operationId: op.run_id, token: '' };
}

/**
 * Mint a fresh ws_token for an existing run.
 *
 * Endpoint: `POST /lca-api/runs/{run_id}/ws-token` body `{userId}`.
 */
export async function lcaRefreshWsToken(
  runId: string,
  userId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const resp = await fetchImpl(
    `/lca-api/runs/${encodeURIComponent(runId)}/ws-token`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${bearer()}`,
      },
      body: JSON.stringify({ userId }),
    },
  );
  if (!resp.ok) {
    throw new Error(`lca ws-token HTTP ${resp.status}`);
  }
  const body = (await resp.json()) as { token: string };
  return body.token;
}