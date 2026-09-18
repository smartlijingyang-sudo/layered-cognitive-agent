// LCA-P1: unit tests for reconnect endpoints.
//
// The LCA gateway HTTP routes live under `/v1/runs/{run_id}/ws-token` and
// `/v1/topics/{topic_id}/running-op` (ADR-0200). The frontend's `/lca-api`
// prefix maps to the gateway root, so these helpers must call
// `/lca-api/v1/...` — a missing `/v1` segment would 404 on the backend.
//
// Copies into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/reconnect.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/reconnect.test.ts

import { afterEach, describe, expect, it, vi } from 'vitest';

import { lcaReconnectToGatewayOperation, lcaRefreshWsToken } from './reconnect';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status: 200,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('lcaRefreshWsToken endpoint', () => {
  it('POSTs /lca-api/v1/runs/{runId}/ws-token with the userId body', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ token: 'jwt-token' }));
    const token = await lcaRefreshWsToken('run_abc', 'user-1', fetchImpl as unknown as typeof fetch);

    expect(token).toBe('jwt-token');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/lca-api/v1/runs/run_abc/ws-token');
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ userId: 'user-1' }));
  });

  it('throws on a non-OK response', async () => {
    const fetchImpl = vi.fn(async () => new Response('nope', { status: 404 }));
    await expect(
      lcaRefreshWsToken('run_dead', 'user-1', fetchImpl as unknown as typeof fetch),
    ).rejects.toThrow('lca ws-token HTTP 404');
  });
});

describe('lcaReconnectToGatewayOperation endpoint', () => {
  it('GETs /lca-api/v1/topics/{topicId}/running-op and returns the run id', async () => {
    const fetchImpl = vi.fn(
      async () => jsonResponse({ running_operation: { run_id: 'run_live' } }),
    );
    const handle = await lcaReconnectToGatewayOperation(
      'topic_1',
      fetchImpl as unknown as typeof fetch,
    );

    expect(handle).toEqual({ operationId: 'run_live', token: '' });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url] = fetchImpl.mock.calls[0] as [string];
    expect(url).toBe('/lca-api/v1/topics/topic_1/running-op');
  });

  it('returns null when the response is not ok', async () => {
    const fetchImpl = vi.fn(async () => new Response('nope', { status: 500 }));
    const handle = await lcaReconnectToGatewayOperation(
      'topic_1',
      fetchImpl as unknown as typeof fetch,
    );
    expect(handle).toBeNull();
  });

  it('returns null when there is no running operation', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ running_operation: null }));
    const handle = await lcaReconnectToGatewayOperation(
      'topic_1',
      fetchImpl as unknown as typeof fetch,
    );
    expect(handle).toBeNull();
  });
});