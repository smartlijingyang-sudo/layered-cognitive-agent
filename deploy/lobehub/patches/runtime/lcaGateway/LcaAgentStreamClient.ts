// LCA-P1: LCA agent-gateway WebSocket client.
//
// Wires against the LCA server-side surface locked by ADR-0200 §1:
//   - URL: <gatewayBase>/v1/runs/<run_id>/ws   (WS_PATH in
//          lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes)
//   - Server messages mirror lca/contracts/transport/gateway_messages.py
//   - Stream event shape mirror lca/contracts/transport/agent_stream_event.py
//     (= the upstream AgentStreamEvent union in @lobechat/agent-gateway-client)
//
// This client deliberately does NOT reuse the upstream
// `AgentStreamClient`: the upstream `buildWsUrl()` hard-codes
// `<base>/ws?operationId=...` for lobehub's own gateway server, which
// is a different wire path. ADR-0200 §1 + §6.1.2 forbid patching the
// vendored lobehub-ui packages, so LCA ships its own transport. The
// public surface (`on` / `off` / `connect` / `disconnect` / `sendInterrupt`
// / `sendToolResult` / `updateToken` / `connectionStatus` +
// `AgentStreamClientEvents`) is intentionally compatible with the
// upstream client so `createLcaGatewayEventHandler` keeps working
// unchanged.
//
// Step A scope (this commit):
//   - URL, auth handshake, control frames, agent_event emit,
//     session/resume/complete, auth_failed/auth_expired.
//   - Heartbeat 30s / 3 missed / 1→30s exponential backoff (ADR-0200 I-AGB-8).
//   - Auto-reconnect with lastEventId resume (server replays from
//     lastEventId; client dedupes by trusting server stream order).
//
// Deferred to Step B:
//   - Resume-buffer dedup window (native `resumeMode` + `resumeBuffer`):
//     we already accept `resumeOnConnect` but currently ignore it because
//     the LCA server emits history in stream order on resume.

import type {
  AgentStreamClientEvents,
  AgentStreamEvent,
  ConnectionStatus,
} from '@lobechat/agent-gateway-client';

// ─── Wire message shapes ─────────────────────────────────────────────
//
// Mirrors lca/contracts/transport/gateway_messages.py. Kept inline so
// the LCA transport does not depend on any other front-end module and
// the SSOT can be checked by tests/architecture/test_lca_wire_parity.py.

interface ClientAuthMessage {
  token: string;
  type: 'auth';
}

interface ClientResumeMessage {
  lastEventId: string;
  type: 'resume';
  wantStatus?: boolean;
}

interface ClientHeartbeatMessage {
  type: 'heartbeat';
}

interface ClientInterruptMessage {
  type: 'interrupt';
}

interface ClientToolResultMessage {
  content: string;
  error?: string;
  state?: Record<string, unknown>;
  success: boolean;
  toolCallId: string;
  type: 'tool_result';
}

type ClientMessage =
  | ClientAuthMessage
  | ClientResumeMessage
  | ClientHeartbeatMessage
  | ClientInterruptMessage
  | ClientToolResultMessage;

interface ServerAuthSuccess {
  type: 'auth_success';
}
interface ServerAuthFailed {
  reason: string;
  type: 'auth_failed';
}
interface ServerAuthExpired {
  type: 'auth_expired';
}
interface ServerHeartbeatAck {
  type: 'heartbeat_ack';
}
interface ServerSessionComplete {
  type: 'session_complete';
}
interface ServerResumeComplete {
  status: 'running' | 'waiting_input' | 'waiting_confirmation' | 'completed' | 'error' | 'interrupted';
  type: 'resume_complete';
}
interface ServerAgentEvent {
  event: AgentStreamEvent;
  id?: string;
  type: 'agent_event';
}

type ServerMessage =
  | ServerAuthSuccess
  | ServerAuthFailed
  | ServerAuthExpired
  | ServerHeartbeatAck
  | ServerSessionComplete
  | ServerResumeComplete
  | ServerAgentEvent;

// ─── Constants ───────────────────────────────────────────────────────

// ADR-0200 §1 + lca/.../wire/routes.py:WS_PATH. Do NOT change without
// touching the server-side route catalog and rerunning the wire parity
// guard (tests/architecture/test_lca_wire_parity.py).
const WS_PATH_TEMPLATE = '/v1/runs/{run_id}/ws';

const HEARTBEAT_INTERVAL_MS = 30_000;
// ADR-0200 I-AGB-8: client_interval=30s, missed_threshold=3, backoff ∈[1s,30s] exp
const HEARTBEAT_MISSED_THRESHOLD = 3;
const RECONNECT_INITIAL_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

// ─── Public options + helpers ────────────────────────────────────────

export interface LcaAgentStreamClientOptions {
  /** LCA gateway base URL (ws://host:port). Token for negotiation. */
  gatewayBase: string;
  /** Operation / run id. */
  operationId: string;
  /** Accepted for API parity with upstream; ignored in Step A (see file header). */
  resumeOnConnect?: boolean;
  /** JWT minted by POST /v1/runs/{run_id}/ws-token. */
  token: string;
}

type Listener<K extends keyof AgentStreamClientEvents> = AgentStreamClientEvents[K];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

// ─── Client ──────────────────────────────────────────────────────────

export class LcaAgentStreamClient {
  private ws: WebSocket | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = RECONNECT_INITIAL_MS;
  private missedHeartbeats = 0;
  private _status: ConnectionStatus = 'disconnected';
  private intentionalDisconnect = false;
  private sessionEnded = false;
  private lastEventId = '0';
  private authed = false;

  private readonly listeners = new Map<keyof AgentStreamClientEvents, Set<(arg: unknown) => void>>();

  constructor(private readonly options: LcaAgentStreamClientOptions) {}

  // ─── Public API (mirrors upstream AgentStreamClient) ─────────────

  get connectionStatus(): ConnectionStatus {
    return this._status;
  }

  override_on<K extends keyof AgentStreamClientEvents>(
    event: K,
    listener: Listener<K>,
  ): () => void {
    let bucket = this.listeners.get(event);
    if (!bucket) {
      bucket = new Set();
      this.listeners.set(event, bucket);
    }
    bucket.add(listener as (arg: unknown) => void);
    return () => {
      bucket?.delete(listener as (arg: unknown) => void);
    };
  }

  on<K extends keyof AgentStreamClientEvents>(
    event: K,
    listener: Listener<K>,
  ): void {
    this.override_on(event, listener);
  }

  off<K extends keyof AgentStreamClientEvents>(
    event: K,
    listener: Listener<K>,
  ): void {
    this.listeners.get(event)?.delete(listener as (arg: unknown) => void);
  }

  connect(): void {
    if (this._status === 'connected' || this._status === 'connecting') return;
    this.intentionalDisconnect = false;
    this.sessionEnded = false;
    this.openSocket();
  }

  disconnect(): void {
    this.intentionalDisconnect = true;
    this.cleanup();
    this.setStatus('disconnected');
    this.emit('disconnected');
  }

  sendInterrupt(): void {
    this.send({ type: 'interrupt' });
  }

  sendToolResult(result: Omit<ClientToolResultMessage, 'type'>): boolean {
    return this.send({ type: 'tool_result', ...result });
  }

  updateToken(token: string): void {
    this.options = { ...this.options, token };
  }

  async reconnect(): Promise<void> {
    this.cleanup();
    this.intentionalDisconnect = false;
    this.sessionEnded = false;
    this.reconnectDelay = RECONNECT_INITIAL_MS;
    this.openSocket();
  }

  // ─── Internal: socket lifecycle ──────────────────────────────────

  private buildWsUrl(): string {
    const base = this.options.gatewayBase.replace(/\/+$/, '');
    return `${base}${WS_PATH_TEMPLATE.replace('{run_id}', encodeURIComponent(this.options.operationId))}`;
  }

  private openSocket(): void {
    if (typeof WebSocket === 'undefined') {
      this.emit('error', new Error('WebSocket is not available in this environment'));
      return;
    }
    this.setStatus('connecting');
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.buildWsUrl());
    } catch (err) {
      this.emit('error', err instanceof Error ? err : new Error(String(err)));
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.setStatus('authenticating');
      // ADR-0200 I-AGB-7: every LCA WS session begins with an auth frame
      // carrying the purpose-bound JWT. Resume follows auth_success so the
      // server knows whether to replay history.
      this.sendRaw({ type: 'auth', token: this.options.token });
    };
    ws.onmessage = (event) => {
      this.handleFrame(event.data);
    };
    ws.onerror = (event) => {
      // onerror is followed by onclose; defer error emit to onclose
      // so we don't double-report and we have a stable error shape.
      this.pendingError =
        (event as ErrorEvent).message
          ? new Error((event as ErrorEvent).message)
          : new Error('WebSocket error');
    };
    ws.onclose = () => {
      const pending = this.pendingError;
      this.pendingError = null;
      this.cleanupSocket();
      if (pending) this.emit('error', pending);
      if (this.sessionEnded || this.intentionalDisconnect) {
        this.setStatus('disconnected');
        this.emit('disconnected');
        return;
      }
      this.scheduleReconnect();
    };
  }

  private pendingError: Error | null = null;

  // ─── Internal: server frame dispatch ────────────────────────────

  private handleFrame(raw: unknown): void {
    let parsed: unknown;
    try {
      parsed = typeof raw === 'string' ? JSON.parse(raw) : null;
    } catch {
      this.emit('error', new Error('LCA gateway frame is not valid JSON'));
      return;
    }
    if (!isRecord(parsed) || typeof parsed.type !== 'string') {
      this.emit('error', new Error('LCA gateway frame missing type discriminator'));
      return;
    }
    const message = parsed as ServerMessage;
    switch (message.type) {
      case 'auth_success': {
        this.authed = true;
        this.setStatus('connected');
        this.emit('connected');
        // Send resume right after auth so the server can replay history
        // before we treat the stream as live.
        this.sendRaw({
          type: 'resume',
          lastEventId: this.lastEventId,
          wantStatus: true,
        });
        this.startHeartbeat();
        return;
      }
      case 'auth_failed': {
        this.emit('auth_failed', typeof message.reason === 'string' ? message.reason : 'unknown');
        this.disconnect();
        return;
      }
      case 'auth_expired': {
        // The server keeps the socket open; listeners refresh token,
        // call updateToken(), then reconnect().
        this.stopHeartbeat();
        this.authed = false;
        this.emit('auth_expired');
        return;
      }
      case 'heartbeat_ack': {
        this.missedHeartbeats = 0;
        return;
      }
      case 'agent_event': {
        if (typeof message.id === 'string') this.lastEventId = message.id;
        this.emit('agent_event', message.event);
        return;
      }
      case 'resume_complete': {
        this.emit('resume_complete', message.status);
        return;
      }
      case 'session_complete': {
        this.sessionEnded = true;
        this.emit('session_complete');
        this.disconnect();
        return;
      }
      default: {
        const _exhaustive: never = message;
        void _exhaustive;
      }
    }
  }

  // ─── Internal: heartbeat ────────────────────────────────────────

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.missedHeartbeats = 0;
    this.heartbeatTimer = setInterval(() => {
      if (!this.authed) return;
      this.missedHeartbeats += 1;
      if (this.missedHeartbeats > HEARTBEAT_MISSED_THRESHOLD) {
        // 3 missed heartbeats → socket is unhealthy, tear it down and
        // let the reconnect path take over with lastEventId resume.
        this.cleanupSocket();
        if (!this.intentionalDisconnect && !this.sessionEnded) this.scheduleReconnect();
        return;
      }
      this.sendRaw({ type: 'heartbeat' });
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // ─── Internal: send helpers ─────────────────────────────────────

  private send(message: ClientMessage): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    return this.sendRaw(message);
  }

  private sendRaw(message: ClientMessage): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    try {
      this.ws.send(JSON.stringify(message));
      return true;
    } catch (err) {
      this.emit('error', err instanceof Error ? err : new Error(String(err)));
      return false;
    }
  }

  // ─── Internal: status + emit ────────────────────────────────────

  private setStatus(next: ConnectionStatus): void {
    if (this._status === next) return;
    this._status = next;
    this.emit('status_changed', next);
  }

  private emit<K extends keyof AgentStreamClientEvents>(
    event: K,
    ...args: Parameters<AgentStreamClientEvents[K]>
  ): void {
    const bucket = this.listeners.get(event);
    if (!bucket) return;
    // Snapshot to avoid mutation during iteration if a listener
    // unregisters itself mid-dispatch.
    for (const listener of Array.from(bucket)) {
      try {
        (listener as (...a: unknown[]) => void)(...args);
      } catch (err) {
        // Listener errors must not abort the dispatch loop or break
        // the WebSocket lifecycle. Log to console and continue.
         
        console.error(`[lca-gateway] listener for "${event}" threw:`, err);
      }
    }
  }

  // ─── Internal: reconnect + teardown ────────────────────────────

  private scheduleReconnect(): void {
    if (this.intentionalDisconnect || this.sessionEnded) return;
    if (this.reconnectTimer) return;
    const delay = this.reconnectDelay;
    this.emit('reconnecting', delay);
    this.setStatus('reconnecting');
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, RECONNECT_MAX_MS);
      this.openSocket();
    }, delay);
  }

  private cleanupSocket(): void {
    this.stopHeartbeat();
    this.authed = false;
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        /* socket already closing */
      }
      this.ws = null;
    }
  }

  private cleanup(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.cleanupSocket();
  }
}

export default LcaAgentStreamClient;