// LCA-P1: unit test for LcaAgentStreamClient.
//
// Copies into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient.test.ts
//
// These tests pin two wire contracts:
//   - `isOwnTerminal` guard (terminal agent_event for a sibling operationId
//     must NOT tear down this client's WS session; mirrors upstream
//     `AgentStreamClient.handleFrame` semantics from
//     `.lobehub-upstream/packages/agent-gateway-client/src/client.ts:286-320`).
//   - `sendToolResult` wire shape (the `tool_result` WS frame must carry
//     `idempotencyKey` so the back-end can dedup cross-tab HIL resubmits;
//     see `lca/contracts/transport/gateway_messages.py::ToolResultMessage`
//     and `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/
//     agent_gateway.py::_handle_control_frame`. Without the field the
//     server-side replay dedup is silent because Pydantic's
//     `extra="ignore"` strips it from the parsed dict).

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

// ─── E: sendToolResult wire shape ──────────────────────────────────

describe('LcaAgentStreamClient.sendToolResult wire shape', () => {
  it('forwards idempotencyKey in the tool_result frame when provided', async () => {
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });
    const ws = await connectAndAuth(client);

    const ok = client.sendToolResult({
      toolCallId: 'tc1',
      success: true,
      content: 'answer',
      idempotencyKey: 'idem-abc-123',
    });

    expect(ok).toBe(true);
    const last = ws.sent.at(-1);
    expect(last).toBeDefined();
    const frame = JSON.parse(last as string);
    expect(frame).toMatchObject({
      type: 'tool_result',
      toolCallId: 'tc1',
      success: true,
      content: 'answer',
      idempotencyKey: 'idem-abc-123',
    });
  });

  it('omits idempotencyKey from the tool_result frame when not provided', async () => {
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });
    const ws = await connectAndAuth(client);

    const ok = client.sendToolResult({
      toolCallId: 'tc2',
      success: false,
      content: 'rejected',
      error: 'user said no',
    });

    expect(ok).toBe(true);
    const last = ws.sent.at(-1);
    expect(last).toBeDefined();
    const frame = JSON.parse(last as string);
    expect(frame).toMatchObject({
      type: 'tool_result',
      toolCallId: 'tc2',
      success: false,
      content: 'rejected',
      error: 'user said no',
    });
    expect('idempotencyKey' in frame).toBe(false);
  });

  it('round-trips idempotencyKey unchanged through sendRaw framing', async () => {
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });
    const ws = await connectAndAuth(client);

    client.sendToolResult({
      toolCallId: 'tc3',
      success: true,
      content: 'cross-tab answer',
      idempotencyKey: 'idem-key-tab2',
    });

    const toolResultFrames = ws.sent
      .map((s) => JSON.parse(s))
      .filter((f) => f.type === 'tool_result');
    expect(toolResultFrames).toHaveLength(1);
    expect(toolResultFrames[0].idempotencyKey).toBe('idem-key-tab2');
  });
});

// ─── B: isOwnTerminal guard ───────────────────────────────────────

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
  });

  it('does NOT disconnect on a forwarded error event for a sibling operationId', async () => {
    const client = new LcaAgentStreamClient({
      gatewayBase: 'ws://test.local',
      operationId: 'op-1',
      token: 't',
    });

    const ws = await connectAndAuth(client);

    ws.simulateMessage({
      event: {
        data: { message: 'sibling boom' },
        operationId: 'op-sibling-2',
        stepIndex: 0,
        timestamp: 1,
        type: 'error',
      },
      id: 'ev-sibling-err',
      type: 'agent_event',
    });

    expect(client.connectionStatus).toBe('connected');
    expect((client as unknown as { sessionEnded: boolean }).sessionEnded).toBe(false);
  });

  it('treats legacy terminal events without operationId as this op’s own', async () => {
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
        data: { chunkType: 'text', content: 'sibling text' },
        operationId: 'op-sibling-2',
        stepIndex: 0,
        timestamp: 1,
        type: 'stream_chunk',
      },
      id: 'ev-stream',
      type: 'agent_event',
    });

    expect(events).toHaveLength(1);
    expect(client.connectionStatus).toBe('connected');
    expect((client as unknown as { sessionEnded: boolean }).sessionEnded).toBe(false);
  });
});
