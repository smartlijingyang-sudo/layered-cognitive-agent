// LCA-P1: LCA gateway event handler factory.
//
// The native handler at
// `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler.ts`
// is the canonical AgentStreamEvent consumer. The LCA transport reuses it
// with two overrides:
//   - `runtimeType: 'lca-gateway'` so the shared handler skips mid-stream
//     DB refetches (LCA persists assistant rows only on turn seal, so a
//     mid-run DB read would clobber content the WS stream already rendered).
//   - `messageService: { getMessages: createLcaInMemoryMessagesReader(get) }`
//     so any non-skipped refetch reconciles against `dbMessagesMap` directly
//     — the same surface `dbMessageSelectors.getDbMessageById` walks —
//     instead of the DB.

import { createGatewayEventHandler } from '@/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler';

import { createLcaInMemoryMessagesReader } from './messageService';

/**
 * Build the LCA gateway event handler. Delegates to the shared native
 * handler factory and threads the LCA in-memory reader through
 * `messageService.getMessages`, so mid-run reads return the live store
 * snapshot instead of hollow DB rows.
 *
 * `params` mirrors the native `createGatewayEventHandler` shape; the
 * factory adds the two LCA-specific fields (`runtimeType`,
 * `messageService`) on top of whatever the caller passed.
 */
export const createLcaGatewayEventHandler: typeof createGatewayEventHandler = (get, params) =>
  createGatewayEventHandler(get, {
    ...params,
    messageService: { getMessages: createLcaInMemoryMessagesReader(get) },
    runtimeType: 'lca-gateway',
  });
