"""1:1 port of ``@deepseek-ai/dsh-agent-loop``.

Agent-loop scheduler, ReactLoopAgent driver, runtime-context projection,
and request-reconstruction invariants.
"""

from __future__ import annotations

from lca.layer0_infra.dsh_core.agent_loop.agent import (
    AbortController,
    ReactLoopAgent,
)
from lca.layer0_infra.dsh_core.agent_loop.constants import (
    DEFAULT_MAX_PARALLEL_TOOL_CALLS,
)
from lca.layer0_infra.dsh_core.agent_loop.index import (
    AgentFactory,
    AgentLoop,
    AgentLoopConfig,
    ConfiguredAgentIdentity,
    FactoryOwnership,
    race_abort,
    race_abort_call,
)
from lca.layer0_infra.dsh_core.agent_loop.runtime_context import (
    CLEARED,
    SOURCE,
    ContextSnapshotSection,
    RuntimeContextProjection,
)
from lca.layer0_infra.dsh_core.agent_loop.tool_calls import (
    ExecuteToolCallsResult,
    execute_tool_calls,
)

__all__ = [
    # runtime-context
    "CLEARED",
    # constants
    "DEFAULT_MAX_PARALLEL_TOOL_CALLS",
    "SOURCE",
    # agent
    "AbortController",
    # index
    "AgentFactory",
    "AgentLoop",
    "AgentLoopConfig",
    "ConfiguredAgentIdentity",
    "ContextSnapshotSection",
    # tool-calls
    "ExecuteToolCallsResult",
    "FactoryOwnership",
    "ReactLoopAgent",
    "RuntimeContextProjection",
    "execute_tool_calls",
    "race_abort",
    "race_abort_call",
]
