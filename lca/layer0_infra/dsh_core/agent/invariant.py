"""1:1 port of ``@deepseek-ai/dsh-agent/invariant.ts``.

Package-owned agent lifecycle invariants.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------

PACKAGE_NAME = "@deepseek-ai/dsh-agent"

#: Cordis companion plugin name.
name = "agent-invariant"

#: Services required before the companion can register.
inject = ["invariants"]


# ---------------------------------------------------------------------------
# Invariant installer
# ---------------------------------------------------------------------------


def install(ctx: Any, fail: Callable[[str], None]) -> None:
    """Install the agent contribution into its child registration fiber.

    Tracks agent status transitions and fails when a no-op transition
    (same status repeated) is detected.
    """
    last_status: dict[int, str] = {}

    def on_status(payload: Any) -> None:
        agent = payload.agent
        status = payload.status
        agent_id = id(agent)
        previous = last_status.get(agent_id)
        if previous == status:
            fail(f"agent/status repeated {status} (no-op transition)")
        last_status[agent_id] = status

    ctx.on("agent/status", on_status, global_=True)


# ---------------------------------------------------------------------------
# Apply — register the invariant companion
# ---------------------------------------------------------------------------


async def apply(ctx: Any) -> Callable[[], None]:
    """Register the agent invariant companion.

    Args:
        ctx: Cordis context carrying the invariant service.

    Returns:
        The installed registration's disposer after setup succeeds.
    """
    invariants = ctx.require("invariants")
    return invariants.register(PACKAGE_NAME, install)
