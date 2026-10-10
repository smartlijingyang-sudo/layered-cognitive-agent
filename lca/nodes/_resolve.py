"""Shared typed-port / runtime-carrier resolve helpers for node executors.

Converges the _resolve_port / _resolve_state copies that used to live
in each node module (delegate.compose, think.llm.persist, think.llm.invoke,
think.decision.parse, think.history.assemble). One Module, one Interface:
the fail-loud contract at the typed boundary lives here, so a change to the
lookup order or the error wording is fixed once, fixed everywhere.

The node argument is the node's dotted scope prefix (e.g.
"llm.persist"); it is interpolated verbatim into the TypeError so
fail-loud tracebacks keep pointing at the node that declared the port.

RA-118 also converged the ``_resolve_writer`` two-shape probe here:
``think.llm.persist`` (fail-loud) and ``concept.effect.execute``
(fail-soft) shared the same attribute-then-``.get`` ritual with
different missing-writer semantics; ``resolve_writer`` makes that
difference an explicit ``required`` flag.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName


def resolve_typed_port(name: PortName, *, input: NodeInput, node: str) -> Any:
    """Pull a declared port from input.port_values; missing → TypeError.

    Typed-port-only read. Runtime-carrier resources (e.g. state) use
    resolve_runtime_state instead so the plan validator sees an
    empty declared_inputs set and the kernel-carrier flow remains
    unimpeded.
    """
    value = input.port_values.get(name)
    if value is None:
        raise TypeError(f"{node}: '{name}' port must be supplied via input.port_values")
    return value


def resolve_typed_port_or_runtime(
    name: PortName, *, input: NodeInput, context: NodeContext, node: str
) -> Any:
    """Read a declared port from input.port_values or context.runtime.

    Mirror the think.shortcut convention: runtime is a namespace object;
    resolve by attribute first, then mapping-style .get.
    """
    value = input.port_values.get(name)
    if value is None and hasattr(context, "runtime") and context.runtime is not None:
        value = getattr(context.runtime, name, None)
        if value is None and hasattr(context.runtime, "get"):
            value = context.runtime.get(name)
    if value is None:
        raise TypeError(
            f"{node}: '{name}' port must be supplied via input.port_values or context.runtime"
        )
    return value


def resolve_writer(*, context: NodeContext, node: str, required: bool) -> Any:
    """Resolve the run-scoped writer off ``context.runtime``.

    Two-shape probe (attribute first, then mapping-style ``.get``) —
    the same ritual ``resolve_typed_port_or_runtime`` uses.

    ``required=True`` (fail-loud, e.g. ``think.llm.persist``): a missing
    writer raises ``TypeError`` naming the node.
    ``required=False`` (fail-soft, e.g. ``concept.effect.execute``): a
    missing writer returns ``None`` so legacy harnesses / unit fixtures
    without a bound writer keep working (the call site's debug-log
    branch stays load-bearing).
    """
    runtime = getattr(context, "runtime", None)
    writer = getattr(runtime, "writer", None) if runtime is not None else None
    if writer is None and runtime is not None and hasattr(runtime, "get"):
        writer = runtime.get("writer")
    if writer is None and required:
        raise TypeError(f"{node}: 'writer' must be supplied via context.runtime")
    return writer


def resolve_runtime_state(*, context: NodeContext, node: str) -> Any:
    """Pull state from the whitelisted kernel runtime carrier."""
    runtime = getattr(context, "runtime", None)
    state_obj = getattr(runtime, "state", None) if runtime is not None else None
    if state_obj is None and runtime is not None and hasattr(runtime, "get"):
        state_obj = runtime.get("state")
    if state_obj is None:
        raise TypeError(f"{node}: 'state' must be supplied via context.runtime")
    return state_obj
