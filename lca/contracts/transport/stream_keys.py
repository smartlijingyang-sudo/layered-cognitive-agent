"""Redis key naming for the agent runtime event stream.

These constants are 1:1 with `apps/server/src/modules/AgentRuntime/StreamEventManager.ts:139-141`
in the native LobeHub implementation. They are the single source of truth
for the wire-compat Redis layout.
"""

STREAM_KEY_PREFIX: str = "agent_runtime_stream"

STREAM_RETENTION_SECONDS: int = 2 * 3600  # 2 hours

STREAM_MAXLEN: str = "~1000"  # approximate trim, same as native


def stream_key(operation_id: str) -> str:
    """Build the Redis Stream key for a given operation id.

    The native code uses `agent_runtime_stream:<operationId>`.
    See `StreamEventManager.ts:174` `streamKey = `${STREAM_PREFIX}:${operationId}``.
    """
    return f"{STREAM_KEY_PREFIX}:{operation_id}"
