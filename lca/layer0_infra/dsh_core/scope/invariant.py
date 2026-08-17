"""Package-owned scoped-dispatch invariants.

1:1 port of ``@deepseek-ai/dsh-scope/invariant.ts``.

Validates that scope-filtered events are dispatched with the correct
scope carrier, and that the carrier key matches the event's subject.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.layer0_infra.dsh_core.scope import carrier_key_of, is_scope_carrier
from lca.layer0_infra.dsh_core.scope.scoped_events import (
    _UNDEFINED,
    scoped_subject_resolver_for,
)

PACKAGE_NAME = "@deepseek-ai/dsh-scope"

InvariantFailure = Callable[[str], None]


def install(ctx: Any, fail: InvariantFailure) -> None:
    """Install the scoped-dispatch contribution into the context."""

    def on_dispatch(event_name: str, args: tuple[Any, ...], this_arg: Any) -> None:
        subject_of = scoped_subject_resolver_for(event_name)
        if subject_of is _UNDEFINED:
            return  # not a scope-filtered event
        if not is_scope_carrier(this_arg):
            fail(
                f'"{event_name}" is a scope-filtered event but was dispatched '
                "without a scope carrier — pass scope_target(base, subject) as "
                "the dispatch thisArg (agent events: use agent_events(ctx, agent))",
            )
            return
        if subject_of is not None and carrier_key_of(this_arg) is not subject_of(args):
            fail(
                f'"{event_name}" was dispatched with a scope carrier keyed to a '
                "DIFFERENT subject than its arguments name — the carrier key and "
                "the event's subject must be the same object "
                "(use agent_events(ctx, agent))",
            )

    ctx.on("internal/dispatch", on_dispatch, global_=True)


def apply(ctx: Any) -> Callable[[], None]:
    """Register the scope invariant companion.

    Returns the installed registration's disposer.
    """
    ctx.invariants.register(PACKAGE_NAME, install)
    return lambda: None
