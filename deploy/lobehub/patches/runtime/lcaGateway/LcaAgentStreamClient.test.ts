// LCA-P1: unit test for LcaAgentStreamClient.tool_result wire shape.
//
// Copied into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient.test.ts
//
// Pins Gap D: the `tool_result` WS frame must carry `idempotencyKey` so
// the back-end can dedup cross-tab HIL resubmits. See
// ``lca/contracts/transport/gateway_messages.py::ToolResultMessage``
// and ``lca/plugins/transport/webserver/handlers/runs/terminal/streaming/
// agent_gateway.py::_handle_control_frame``. Without the field the
// server-side replay dedup is silent (Pydantic ``extra="ignore"`` strips
// it from the parsed dict), and a same-key resend of an HIL answer
// re-runs the resume handler instead of being deduped.

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
    // Last frame must be the tool_result message — auth + resume are
    // sent first, so the LAST sent entry is the one we just dispatched.
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
    // Pin the byte-compat shape: the back-end reads
    // `msg.get('idempotencyKey', '')` from the raw JSON. If TS ever
    // starts camel-casing differently or omitting the key, dedup
    // silently breaks.
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
