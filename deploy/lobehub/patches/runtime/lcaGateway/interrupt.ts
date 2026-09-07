// LCA-P1: control-frame helpers for an open LCA WS.
//
// The native AgentStreamClient exposes `sendInterrupt()` and
// `sendToolResult(...)` for client-to-server control frames (see
// `packages/agent-gateway-client/src/client.ts`). We keep a small
// registry of open connections keyed by operationId so callers can
// trigger a control frame without holding the AgentStreamClient
// reference. The registry is populated by connect.ts at the call site
// (chat store wiring) and cleared on disconnect.

interface LcaControlConnection {
  sendInterrupt: () => void;
  sendToolResult: (payload: {
    toolCallId: string;
    success: boolean;
    content: string;
    state?: Record<string, unknown>;
  }) => void;
}

const registry: Map<string, LcaControlConnection> = new Map();

export function registerLcaGatewayConnection(
  operationId: string,
  conn: LcaControlConnection,
): () => void {
  registry.set(operationId, conn);
  return () => {
    if (registry.get(operationId) === conn) {
      registry.delete(operationId);
    }
  };
}

export function lcaInterruptGateway(operationId: string): boolean {
  const conn = registry.get(operationId);
  if (!conn) return false;
  conn.sendInterrupt();
  return true;
}

export interface LcaToolResultPayload {
  toolCallId: string;
  success: boolean;
  content: string;
  state?: Record<string, unknown>;
}

export function lcaSendToolResult(
  operationId: string,
  payload: LcaToolResultPayload,
): boolean {
  const conn = registry.get(operationId);
  if (!conn) return false;
  conn.sendToolResult(payload);
  return true;
}

export function _resetLcaConnectionsForTests(): void {
  registry.clear();
}