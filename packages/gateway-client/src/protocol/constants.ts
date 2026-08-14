/** Default gateway URL for local dev. */
export const DEFAULT_GATEWAY_URL = 'http://127.0.0.1:8765';

/** Heartbeat interval in ms. */
export const HEARTBEAT_INTERVAL_MS = 30_000;

/** Force reconnect after N missed heartbeat acks. */
export const MAX_MISSED_HEARTBEATS = 3;

/** Initial reconnect delay in ms. */
export const INITIAL_RECONNECT_DELAY_MS = 1_000;

/** Max reconnect delay in ms (exponential backoff cap). */
export const MAX_RECONNECT_DELAY_MS = 30_000;

/** Default HTTP request timeout in ms. */
export const DEFAULT_HTTP_TIMEOUT_MS = 90_000;
