/**
 * WebSocket client for the LCA device gateway.
 *
 * Handles auth handshake, heartbeat keepalive, automatic reconnect
 * with exponential backoff, and event dispatch for incoming messages.
 */

import { randomUUID } from 'node:crypto';
import { EventEmitter } from 'node:events';
import os from 'node:os';

import WebSocket from 'ws';

import {
  DEFAULT_GATEWAY_URL,
  HEARTBEAT_INTERVAL_MS,
  INITIAL_RECONNECT_DELAY_MS,
  MAX_MISSED_HEARTBEATS,
  MAX_RECONNECT_DELAY_MS,
} from '../protocol/constants.js';
import type {
  AuthFailedMessage,
  ClientMessage,
  ConnectionStatus,
  RpcRequestMessage,
  ServerMessage,
  ToolCallRequestMessage,
} from '../protocol/types.js';

export interface Logger {
  debug(msg: string, ...args: unknown[]): void;
  info(msg: string, ...args: unknown[]): void;
  warn(msg: string, ...args: unknown[]): void;
  error(msg: string, ...args: unknown[]): void;
}

const noopLogger: Logger = {
  debug: () => {},
  info: () => {},
  warn: () => {},
  error: () => {},
};

export interface GatewayClientOptions {
  gatewayUrl?: string;
  deviceId?: string;
  connectionId?: string;
  token: string;
  tokenType?: 'apiKey' | 'jwt' | 'serviceToken';
  channel?: string;
  home?: string;
  workspace?: string;
  autoReconnect?: boolean;
  logger?: Logger;
}

export interface GatewayClientEvents {
  connected: () => void;
  disconnected: () => void;
  auth_failed: (reason: string) => void;
  tool_call_request: (request: ToolCallRequestMessage) => void;
  rpc_request: (request: RpcRequestMessage) => void;
  status_changed: (status: ConnectionStatus) => void;
  reconnecting: (delayMs: number) => void;
  error: (error: Error) => void;
}

export class GatewayClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = INITIAL_RECONNECT_DELAY_MS;
  private missedHeartbeats = 0;
  private status: ConnectionStatus = 'disconnected';
  private intentionalDisconnect = false;

  private readonly deviceId: string;
  private readonly connectionId: string;
  private readonly channel?: string;
  private readonly gatewayUrl: string;
  private token: string;
  private readonly tokenType: string;
  private readonly home: string;
  private readonly workspace: string;
  private readonly logger: Logger;
  private readonly autoReconnect: boolean;

  constructor(options: GatewayClientOptions) {
    super();
    this.gatewayUrl = options.gatewayUrl ?? DEFAULT_GATEWAY_URL;
    this.deviceId = options.deviceId ?? randomUUID();
    this.connectionId = options.connectionId ?? randomUUID();
    this.token = options.token;
    this.tokenType = options.tokenType ?? 'serviceToken';
    this.channel = options.channel;
    this.home = options.home ?? os.homedir();
    this.workspace = options.workspace ?? os.homedir();
    this.logger = options.logger ?? noopLogger;
    this.autoReconnect = options.autoReconnect ?? true;
  }

  // ─── Public API ───

  get connectionStatus(): ConnectionStatus {
    return this.status;
  }

  get currentDeviceId(): string {
    return this.deviceId;
  }

  get currentConnectionId(): string {
    return this.connectionId;
  }

  override on<K extends keyof GatewayClientEvents>(
    event: K,
    listener: GatewayClientEvents[K],
  ): this {
    return super.on(event, listener);
  }

  override emit<K extends keyof GatewayClientEvents>(
    event: K,
    ...args: Parameters<GatewayClientEvents[K]>
  ): boolean {
    return super.emit(event, ...args);
  }

  updateToken(token: string): void {
    this.token = token;
  }

  async connect(): Promise<void> {
    if (this.status === 'connected' || this.status === 'connecting') return;
    this.intentionalDisconnect = false;
    this.doConnect();
  }

  async reconnect(): Promise<void> {
    this.cleanup();
    this.intentionalDisconnect = false;
    this.reconnectDelay = INITIAL_RECONNECT_DELAY_MS;
    this.doConnect();
  }

  async disconnect(): Promise<void> {
    this.intentionalDisconnect = true;
    this.cleanup();
    this.setStatus('disconnected');
  }

  sendToolCallResponse(
    requestId: string,
    result: { success: boolean; content: string; state?: unknown; error?: string },
  ): void {
    this.sendMessage({ type: 'tool_call_response', requestId, result });
  }

  sendRpcResponse(
    requestId: string,
    result: { success: boolean; data?: unknown; error?: string },
  ): void {
    this.sendMessage({ type: 'rpc_response', requestId, result });
  }

  // ─── Connection internals ───

  private doConnect(): void {
    this.clearReconnectTimer();
    this.setStatus('connecting');

    try {
      const url = this.buildWsUrl();
      this.logger.debug(`connecting to ${url}`);
      const ws = new WebSocket(url);
      ws.on('open', this.handleOpen);
      ws.on('message', this.handleMessage);
      ws.on('close', this.handleClose);
      ws.on('error', this.handleError);
      this.ws = ws;
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.logger.error(`failed to create WebSocket: ${msg}`);
      this.setStatus('disconnected');
      if (this.autoReconnect) this.scheduleReconnect();
      else this.emit('disconnected');
    }
  }

  private buildWsUrl(): string {
    const proto = this.gatewayUrl.startsWith('https') || this.gatewayUrl.startsWith('wss') ? 'wss' : 'ws';
    const host = this.gatewayUrl.replace(/^(https?|wss?):\/\//, '');
    const params = new URLSearchParams({
      deviceId: this.deviceId,
      connectionId: this.connectionId,
      hostname: os.hostname(),
      platform: process.platform,
    });
    if (this.channel) params.set('channel', this.channel);
    return `${proto}://${host}/api/device/ws?${params}`;
  }

  private handleOpen = (): void => {
    this.logger.info('WebSocket open, sending auth');
    this.reconnectDelay = INITIAL_RECONNECT_DELAY_MS;
    this.setStatus('authenticating');
    this.sendMessage({
      type: 'auth',
      token: this.token,
      tokenType: this.tokenType as 'apiKey' | 'jwt' | 'serviceToken',
      home: this.home,
      workspace: this.workspace,
    });
  };

  private handleMessage = (data: WebSocket.Data): void => {
    try {
      const msg = JSON.parse(String(data)) as ServerMessage;
      switch (msg.type) {
        case 'auth_success':
          this.logger.info('authenticated');
          this.setStatus('connected');
          this.startHeartbeat();
          this.emit('connected');
          break;
        case 'auth_failed':
          this.logger.error(`auth failed: ${(msg as AuthFailedMessage).reason}`);
          this.emit('auth_failed', (msg as AuthFailedMessage).reason);
          this.disconnect();
          break;
        case 'heartbeat_ack':
          this.missedHeartbeats = 0;
          break;
        case 'tool_call_request':
          this.emit('tool_call_request', msg as ToolCallRequestMessage);
          break;
        case 'rpc_request':
          this.emit('rpc_request', msg as RpcRequestMessage);
          break;
        default:
          this.logger.warn(`unknown message type: ${(msg as { type: string }).type}`);
      }
    } catch (error) {
      this.logger.error(`failed to parse message: ${String(error)}`);
    }
  };

  private handleClose = (_code: number, _reason: Buffer): void => {
    this.logger.info('WebSocket closed');
    this.stopHeartbeat();
    this.ws = null;
    if (!this.intentionalDisconnect && this.autoReconnect) {
      this.setStatus('reconnecting');
      this.scheduleReconnect();
    } else {
      this.setStatus('disconnected');
      this.emit('disconnected');
    }
  };

  private handleError = (error: Error): void => {
    this.logger.error(`WebSocket error: ${error.message}`);
    this.emit('error', error);
  };

  // ─── Heartbeat ───

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.missedHeartbeats = 0;
    this.heartbeatTimer = setInterval(() => {
      this.missedHeartbeats++;
      if (this.missedHeartbeats > MAX_MISSED_HEARTBEATS) {
        this.logger.warn(`missed ${this.missedHeartbeats} heartbeat acks, forcing reconnect`);
        this.closeWebSocket();
        if (this.autoReconnect) {
          this.setStatus('reconnecting');
          this.scheduleReconnect();
        } else {
          this.setStatus('disconnected');
          this.emit('disconnected');
        }
        return;
      }
      this.sendMessage({ type: 'heartbeat' });
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // ─── Reconnect ───

  private scheduleReconnect(): void {
    this.clearReconnectTimer();
    this.logger.info(`reconnecting in ${this.reconnectDelay}ms`);
    this.emit('reconnecting', this.reconnectDelay);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.doConnect();
    }, this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  // ─── Helpers ───

  private setStatus(status: ConnectionStatus): void {
    if (this.status === status) return;
    this.status = status;
    this.emit('status_changed', status);
  }

  private sendMessage(data: ClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  private closeWebSocket(): void {
    if (!this.ws) return;
    const ws = this.ws;
    ws.off('open', this.handleOpen);
    ws.off('message', this.handleMessage);
    ws.off('close', this.handleClose);
    ws.off('error', this.handleError);
    try {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close(1000, 'client disconnect');
      }
    } catch {
      // ignore close errors
    }
    this.ws = null;
  }

  private cleanup(): void {
    this.stopHeartbeat();
    this.clearReconnectTimer();
    this.closeWebSocket();
  }
}
