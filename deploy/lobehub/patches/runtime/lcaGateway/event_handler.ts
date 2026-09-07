// LCA-P1: re-export of the native gateway event handler.
//
// The native handler at
// `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler.ts`
// is the canonical AgentStreamEvent consumer. It is wired against the
// agent-gateway-client `on(...)` callback shape, which LCA's
// AgentStreamClient (Task 8) already implements. We re-export so the
// patched chat store can `import { createLcaGatewayEventHandler }
// from '@/store/chat/agents/transports/lcaGateway/event_handler'`.
//
// When the patch is not applied, the chat store falls back to the
// legacy SSE path (retired in PR-4).

export { createGatewayEventHandler as createLcaGatewayEventHandler } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler';