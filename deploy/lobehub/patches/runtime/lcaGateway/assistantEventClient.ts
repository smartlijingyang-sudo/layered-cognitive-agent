// LCA avatar event WebSocket client.
//
// Connects to `/v1/assistants/{id}/events` (proxied as
// `/lca-api/v1/assistants/{id}/events`), authenticates with the same
// first-frame `{type:'auth', token}` handshake the gateway WS uses
// (lca/plugins/avatar/events.py — ADR-0269 §6 / spec §10), and
// broadcasts `avatar_updated` / `avatar_video_ready` to the window so
// `AssistantAvatarImage` can refetch the active avatar.

export type AssistantEvent =
  | { type: 'avatar_updated'; assistant_id: string; payload: Record<string, unknown> }
  | { type: 'avatar_video_ready'; assistant_id: string; payload: Record<string, unknown> };

const EVENT_PATH = (assistantId: string) =>
  `/lca-api/v1/assistants/${encodeURIComponent(assistantId)}/events`;

function authToken(): string {
  const envToken =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env
          ?.NEXT_PUBLIC_LCA_TOKEN
      : undefined;
  return envToken && envToken.length > 0 ? envToken : 'lca-local';
}

export class AssistantEventClient {
  private ws: WebSocket | null = null;
  private retry = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalDisconnect = false;

  constructor(private assistantId: string) {}

  connect(): void {
    if (this.intentionalDisconnect) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(
      `${proto}://${location.host}${EVENT_PATH(this.assistantId)}`,
    );
    this.ws.onopen = () => {
      this.retry = 0;
      // 首帧 JWT 握手（与网关 WS 同型）；dev_mode 下服务端忽略 token。
      this.ws?.send(JSON.stringify({ type: 'auth', token: authToken() }));
    };
    this.ws.onmessage = (ev) => {
      try {
        this.handle(JSON.parse(String(ev.data)) as AssistantEvent);
      } catch {
        /* 忽略非 JSON 帧 */
      }
    };
    this.ws.onclose = () => {
      this.ws = null;
      if (this.intentionalDisconnect) return;
      const delay = 2000 * Math.min(2 ** this.retry++, 10);
      this.reconnectTimer = setTimeout(() => this.connect(), delay);
    };
    this.ws.onerror = () => {
      // onerror 后必随 onclose；重连统一由 onclose 处理。
    };
  }

  disconnect(): void {
    this.intentionalDisconnect = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  private handle(event: AssistantEvent): void {
    if (event.type === 'avatar_updated' || event.type === 'avatar_video_ready') {
      // AssistantAvatarImage 监听该事件并清缓存、重新 GET /avatar。
      window.dispatchEvent(new CustomEvent('lca-assistant-avatar-changed', { detail: event }));
    }
  }
}

export default AssistantEventClient;