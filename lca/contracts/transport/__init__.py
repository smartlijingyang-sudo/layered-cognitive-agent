"""Wire-protocol types mirroring the native LobeHub AgentGateway protocol.

This module is importlinter-clean: it depends only on pydantic and the
standard library, never on `lca.infrastructure`, `lca.plugins`, `lca.cognition`,
`lca.runtime`, `lca.agent`, or `lca.application`. Mirror of
`lobehub-ui/packages/agent-gateway-client/src/types.ts`.
"""

from lca.contracts.transport import agent_stream_event, gateway_messages, stream_keys

__all__ = ("agent_stream_event", "gateway_messages", "stream_keys")
