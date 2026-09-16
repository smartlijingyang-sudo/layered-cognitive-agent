// LCA-P1: unit test for LcaAgentStreamClient.
//
// Copies into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient.test.ts
//
// These tests pin the isOwnTerminal guard added to `handleFrame` so a
// terminal agent_event for a sibling operationId cannot tear down this
// client's WS session. Today the LCA server is single-op per WS, so the
// regression surface is purely defensive (mirrors upstream
// `AgentStreamClient.handleFrame` semantics from
// `.lobehub-upstream/packages/agent-gateway-client/src/client.ts:286-320`).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LcaAgentStreamClient } from './LcaAgentStreamClient';

// ─── Mock WebSocket ────────────────────────────────────────────────

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;

  sent: string[] = [];

  constructor(public url: string) {
    // Auto-connect in next tick so client.onopen fires after connect().
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.({});
    }, 0);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(_code?: number, _reason?: string): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({});
  }

  simulateMessage(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateClose(): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({});
  }
}

let mockWsInstances: MockWebSocket[] = [];

beforeEach(() => {
  mockWsInstances = [];
  vi.stubGlobal(
    'WebSocket',
    Object.assign(
      class extends MockWebSocket {
        constructor(url: string) {
          super(url);
          mockWsInstances.push(this);
        }
      },
      {
        CLOSED: MockWebSocket.CLOSED,
        CLOSING: MockWebSocket.CLOSING,
        CONNECTING: MockWebSocket.CONNECTING,
        OPEN: MockWebSocket.OPEN,
      },
    ),
  );
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function getLatestWs(): MockWebSocket {
  const ws = mockWsInstances.at(-1);
  if (!ws) throw new Error('No mock WebSocket was created');
  return ws;
}

async function connectAndAuth(client: LcaAgentStreamClient): Promise<MockWebSocket> {
  client.connect();
  await vi.advanceTimersByTimeAsync(1);
  const ws = getLatestWs();
  ws.simulateMessage({ type: 'auth_success' });
  return ws;
}

describe('LcaAgentStreamClient.isOwnTerminal guard', () => {
  it('disconnects on agent_runtime_end for this operationId', async () => {
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });
    const events: unknown[] = [];
    client.on('agent_event', (e) => events.push(e));

    const ws = await connectAndAuth(client);

    ws.simulateMessage({
      event: {
        data: { reason: 'completed' },
        operationId: 'op-1',
        stepIndex: 0,
        timestamp: 1,
        type: 'agent_runtime_end',
      },
      id: 'ev-1',
      type: 'agent_event',
    });

    expect(events).toHaveLength(1);
    expect(client.connectionStatus).toBe('disconnected');
    expect((client as unknown as { sessionEnded: boolean }).sessionEnded).toBe(true);
  });

  it('disconnects on error event for this operationId', async () => {
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });

    const ws = await connectAndAuth(client);

    ws.simulateMessage({
      event: {
        data: { message: 'boom' },
        operationId: 'op-1',
        stepIndex: 0,
        timestamp: 1,
        type: 'error',
      },
      id: 'ev-1',
      type: 'agent_event',
    });

    expect(client.connectionStatus).toBe('disconnected');
    expect((client as unknown as { sessionEnded: boolean }).sessionEnded).toBe(true);
  });

  it('does NOT disconnect on a forwarded agent_runtime_end for a sibling operationId', async () => {
    // Single-connection WS multiplexing may eventually forward sibling
    // terminal events onto this client's channel. The owner op's
    // terminal ends the session; a sibling's must NOT.
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });
    const events: unknown[] = [];
    client.on('agent_event', (e) => events.push(e));

    const ws = await connectAndAuth(client);

    ws.simulateMessage({
      event: {
        data: { reason: 'completed' },
        operationId: 'op-sibling-2',
        stepIndex: 0,
        timestamp: 1,
        type: 'agent_runtime_end',
      },
      id: 'ev-sibling',
      type: 'agent_event',
    });

    // Sibling terminal still surfaces so a future member handler can
    // finalize that operation.
    expect(events).toHaveLength(1);
    // But the WS stays open and sessionEnded stays false.
    expect(client.connectionStatus).toBe('connected');
    expect((client as unknown as { sessionEnded: boolean }).sessionEnded).toBe(false);

    // The owner op's own terminal still ends the session.
    ws.simulateMessage({
      event: {
        data: { reason: 'completed' },
        operationId: 'op-1',
        stepIndex: 1,
        timestamp: 2,
        type: 'agent_runtime_end',
      },
      id: 'ev-own',
      type: 'agent_event',
    });
    expect(client.connectionStatus).toBe('disconnected');
    expect((client as unknown as { sessionEnded: boolean }).sessionEnded).toBe(true);
  });

  it('does NOT disconnect on a forwarded error event for a sibling operationId', async () => {
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });
    const events: unknown[] = [];
    client.on('agent_event', (e) => events.push(e));

    const ws = await connectAndAuth(client);

    ws.simulateMessage({
      event: {
        data: { message: 'sibling failed' },
        operationId: 'op-sibling-2',
        stepIndex: 0,
        timestamp: 1,
        type: 'error',
      },
      id: 'ev-sibling',
      type: 'agent_event',
    });

    expect(events).toHaveLength(1);
    expect(client.connectionStatus).toBe('connected');
    expect((client as unknown as { sessionEnded: boolean }).sessionEnded).toBe(false);
  });

  it('treats legacy terminal events without operationId as this op\u2019s own', async () => {
    // Pre-multiplexing LCA server frames never carried operationId inside
    // the agent_event. The guard falls back to "this op owns it" so legacy
    // streams still terminate the session.
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });

    const ws = await connectAndAuth(client);

    ws.simulateMessage({
      event: {
        data: {},
        // no operationId on purpose
        stepIndex: 0,
        timestamp: 1,
        type: 'agent_runtime_end',
      },
      id: 'ev-legacy',
      type: 'agent_event',
    });

    expect(client.connectionStatus).toBe('disconnected');
    expect((client as unknown as { sessionEnded: boolean }).sessionEnded).toBe(true);
  });

  it('does NOT disconnect on a non-terminal agent_event for a sibling operationId', async () => {
    // Sanity check: non-terminal sibling events have always been safe
    // because the current code never tears down on agent_event at all.
    // This test pins the existing behavior so we notice if a future
    // refactor accidentally broadens the guard to all sibling events.
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });
    const events: unknown[] = [];
    client.on('agent_event', (e) => events.push(e));

    const ws = await connectAndAuth(client);

    ws.simulateMessage({
      event: {
        data: { chunk: 'hello' },
        operationId: 'op-sibling-2',
        stepIndex: 0,
        timestamp: 1,
        type: 'stream_chunk',
      },
      id: 'ev-sibling-chunk',
      type: 'agent_event',
    });

    expect(events).toHaveLength(1);
    expect(client.connectionStatus).toBe('connected');
  });
});
