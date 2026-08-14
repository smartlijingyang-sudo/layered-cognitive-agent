/**
 * WebSocket protocol message types.
 *
 * Wire protocol is compatible with the upstream device-gateway service,
 * but types are owned by LCA — we do not import from upstream.
 */

// ─── Client → Server ───

export interface AuthMessage {
  type: 'auth';
  token: string;
  tokenType?: 'apiKey' | 'jwt' | 'serviceToken';
  home?: string;
  workspace?: string;
}

export interface HeartbeatMessage {
  type: 'heartbeat';
}

export interface ToolCallResponseMessage {
  type: 'tool_call_response';
  requestId: string;
  result: {
    success: boolean;
    content: string;
    state?: unknown;
    error?: string;
  };
}

export interface RpcResponseMessage {
  type: 'rpc_response';
  requestId: string;
  result: {
    success: boolean;
    data?: unknown;
    error?: string;
  };
}

export interface SystemInfoResponseMessage {
  type: 'system_info_response';
  requestId: string;
  result: {
    success: boolean;
    data?: unknown;
    error?: string;
  };
}

export interface AgentRunAckMessage {
  type: 'agent_run_ack';
  operationId: string;
  status: 'accepted' | 'rejected';
  reason?: string;
}

export type ClientMessage =
  | AuthMessage
  | HeartbeatMessage
  | ToolCallResponseMessage
  | RpcResponseMessage
  | SystemInfoResponseMessage
  | AgentRunAckMessage;

// ─── Server → Client ───

export interface AuthSuccessMessage {
  type: 'auth_success';
}

export interface AuthFailedMessage {
  type: 'auth_failed';
  reason: string;
}

export interface HeartbeatAckMessage {
  type: 'heartbeat_ack';
}

export interface ToolCallRequestMessage {
  type: 'tool_call_request';
  requestId: string;
  timeout?: number;
  toolCall: {
    identifier: string;
    apiName: string;
    arguments: string;
    type?: string;
  };
}

export interface RpcRequestMessage {
  type: 'rpc_request';
  requestId: string;
  method: string;
  params?: unknown;
  timeout?: number;
}

export type ServerMessage =
  | AuthSuccessMessage
  | AuthFailedMessage
  | HeartbeatAckMessage
  | ToolCallRequestMessage
  | RpcRequestMessage;

// ─── Shared ───

export type ConnectionStatus =
  | 'disconnected'
  | 'connecting'
  | 'authenticating'
  | 'connected'
  | 'reconnecting';

export interface DeviceInfo {
  deviceId: string;
  hostname: string;
  platform: string;
  home: string;
  workspace: string;
  online: boolean;
  channels: Array<{
    connectionId: string;
    channel: string;
    connectedAt: string;
  }>;
}
