// LCA-P1: re-export of the native gateway event router.
//
// The native router at
// `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventRouter.ts`
// maps each AgentStreamEvent type to a Redux action / state mutation.
// LCA's wire protocol is byte-compat with the native types, so the
// router works unmodified against our WS frames.

export { createGatewayEventRouter as createLcaGatewayEventRouter } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventRouter';