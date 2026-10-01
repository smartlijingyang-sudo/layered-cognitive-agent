"""Shared event-loop staleness guard for MCP transports (package-private).

Both the stdio and streamable-HTTP transports bind to the event loop they were
connected on; a transport queried from a *different* running loop is stale even
if its connection flags still look alive. The check is factored out so the two
transports cannot drift in semantics.
"""

from __future__ import annotations

import asyncio


def loop_mismatch(bound_loop: asyncio.AbstractEventLoop | None) -> bool:
    """Return True when *bound_loop* is set and differs from the running loop.

    When there is no running loop at all (``RuntimeError``), there is nothing
    to compare against, so it reports no mismatch: the transport's own
    connection-state flags (process alive / client open) remain authoritative.
    """
    try:
        curr_loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return bound_loop is not None and bound_loop is not curr_loop
