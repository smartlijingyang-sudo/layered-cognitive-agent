// LCA avatar event WS client — unit tests.
//
// Copies into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/assistantEventClient.test.ts`
// by `lca_assistant_events`; run from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/assistantEventClient.test.ts
//
// Pins three wire contracts:
//   - WS URL: `ws(s)://<host>/lca-api/v1/assistants/{id}/events`
//   - First frame: `{type:'auth', token}` (gateway WS handshake, ADR-0269 §6)
//   - `avatar_updated` / `avatar_video_ready` dispatch a window
//     CustomEvent `lca-assistant-avatar-changed` carrying the event as detail.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AssistantEventClient } from './assistantEventClient';

class MockWebSocket {
  static OPEN = 1;
  OPEN = MockWebSocket.OPEN;
  CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    mockWsInstances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  simulateOpen(): void {
    this.onopen?.();
  }

  simulateMessage(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateClose(): void {
    this.onclose?.();
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
        }
      },
      { OPEN: MockWebSocket.OPEN, CLOSED: MockWebSocket.CLOSED },
    ),
  );
  vi.stubGlobal('location', { protocol: 'http:', host: 'lobe.test' });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function getLatestWs(): MockWebSocket {
  const ws = mockWsInstances.at(-1);
  if (!ws) throw new Error('No mock WebSocket was created');
  return ws;
}

describe('AssistantEventClient', () => {
  it('connects to the avatar events WS and sends the auth frame', () => {
    const client = new AssistantEventClient('assistant_1');
    client.connect();
    const ws = getLatestWs();

    expect(ws.url).toBe('ws://lobe.test/lca-api/v1/assistants/assistant_1/events');
    ws.simulateOpen();
    expect(ws.sent[0]).toBe(JSON.stringify({ type: 'auth', token: 'lca-local' }));
    client.disconnect();
  });

  it('uses wss for https origins', () => {
    vi.stubGlobal('location', { protocol: 'https:', host: 'lobe.test' });
    const client = new AssistantEventClient('assistant_1');
    client.connect();

    expect(getLatestWs().url).toBe('wss://lobe.test/lca-api/v1/assistants/assistant_1/events');
    client.disconnect();
  });

  it('dispatches lca-assistant-avatar-changed on avatar_updated', () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const client = new AssistantEventClient('assistant_1');
    client.connect();
    getLatestWs().simulateOpen();

    getLatestWs().simulateMessage({
      type: 'avatar_updated',
      assistant_id: 'assistant_1',
      payload: { candidate_id: 'cand_1' },
    });

    expect(dispatch).toHaveBeenCalledTimes(1);
    const [dispatched] = dispatch.mock.calls[0] as [CustomEvent];
    expect(dispatched.type).toBe('lca-assistant-avatar-changed');
    expect(dispatched.detail).toEqual({
      type: 'avatar_updated',
      assistant_id: 'assistant_1',
      payload: { candidate_id: 'cand_1' },
    });
    client.disconnect();
  });

  it('dispatches lca-assistant-avatar-changed on avatar_video_ready', () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    const client = new AssistantEventClient('assistant_1');
    client.connect();
    getLatestWs().simulateOpen();

    getLatestWs().simulateMessage({
      type: 'avatar_video_ready',
      assistant_id: 'assistant_1',
      payload: { video_status: 'ready' },
    });

    expect(dispatch).toHaveBeenCalledTimes(1);
    client.disconnect();
  });

  it('reconnects with exponential backoff on close', () => {
    vi.useFakeTimers();
    const client = new AssistantEventClient('assistant_1');
    client.connect();
    getLatestWs().simulateClose();

    expect(mockWsInstances.length).toBe(1);
    vi.advanceTimersByTime(1999);
    expect(mockWsInstances.length).toBe(1);
    vi.advanceTimersByTime(1);
    expect(mockWsInstances.length).toBe(2);
    client.disconnect();
  });

  it('disconnect stops reconnecting', () => {
    vi.useFakeTimers();
    const client = new AssistantEventClient('assistant_1');
    client.connect();
    getLatestWs().simulateClose();
    client.disconnect();

    vi.advanceTimersByTime(60_000);
    expect(mockWsInstances.length).toBe(1);
  });
});