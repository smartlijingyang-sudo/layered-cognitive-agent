/**
 * @lca/gateway-client — gateway communication for LCA devices.
 *
 * Two transports:
 * - GatewayClient: persistent WebSocket for real-time tool calls + RPC
 * - HttpClient: request/response for queries and uploads
 *
 * Protocol types are shared under `protocol/`.
 */

export { HttpClient } from './http/client.js';
export type {
  HttpClientOptions,
  RpcParams,
  ToolCallParams,
  ToolCallResult,
  UploadFilesParams,
} from './http/client.js';
export {
  DEFAULT_GATEWAY_URL,
  DEFAULT_HTTP_TIMEOUT_MS,
  HEARTBEAT_INTERVAL_MS,
  INITIAL_RECONNECT_DELAY_MS,
  MAX_MISSED_HEARTBEATS,
  MAX_RECONNECT_DELAY_MS,
} from './protocol/constants.js';
export {
  GatewayAuthError,
  GatewayConnectionError,
  GatewayTimeoutError,
} from './protocol/errors.js';
export type {
  AgentRunAckMessage,
  AuthFailedMessage,
  AuthMessage,
  AuthSuccessMessage,
  ClientMessage,
  ConnectionStatus,
  DeviceInfo,
  HeartbeatAckMessage,
  HeartbeatMessage,
  RpcRequestMessage,
  RpcResponseMessage,
  ServerMessage,
  SystemInfoResponseMessage,
  ToolCallRequestMessage,
  ToolCallResponseMessage,
} from './protocol/types.js';
export { GatewayClient } from './ws/client.js';
export type { GatewayClientEvents, GatewayClientOptions, Logger } from './ws/client.js';
