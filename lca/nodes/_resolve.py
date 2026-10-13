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

RA-119 mirrored the ``required`` flag onto ``resolve_runtime_state`` so the
fail-soft ``concept.effect.execute`` probes converge here too instead of
hand-rolling the two-shape probe.

RA-123 converged the ``adapter`` two-shape probe here as well:
``think.llm.invoke`` (fail-loud) and ``reflect.memory_extract``
(fail-soft) hand-rolled the same attribute-then-``.get`` ritual with
divergent missing semantics; ``resolve_runtime_adapter`` makes that
difference an explicit ``required`` flag, completing the RA-118/119 tail.
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


def resolve_runtime_state(*, context: NodeContext, node: str, required: bool = True) -> Any:
    """Pull state from the whitelisted kernel runtime carrier.

    Two-shape probe (attribute first, then mapping-style ``.get``) — the
    same ritual ``resolve_writer`` uses.

    ``required=True`` (fail-loud, e.g. ``think.llm.persist``): a missing
    state raises ``TypeError`` naming the node.
    ``required=False`` (fail-soft, e.g. ``concept.effect.execute``): a
    missing state returns ``None`` so the call site's own acceptance gate
    (``isinstance(runtime_state, AgentState)`` / ``getattr(state, "step",
    0)``) stays load-bearing.
    """
    runtime = getattr(context, "runtime", None)
    state_obj = getattr(runtime, "state", None) if runtime is not None else None
    if state_obj is None and runtime is not None and hasattr(runtime, "get"):
        state_obj = runtime.get("state")
    if state_obj is None and required:
        raise TypeError(f"{node}: 'state' must be supplied via context.runtime")
    return state_obj


def resolve_runtime_adapter(*, context: NodeContext, node: str, required: bool = True) -> Any:
    """Pull the LLM adapter from the whitelisted kernel runtime carrier.

    Two-shape probe (attribute first, then mapping-style ``.get``) — the
    same ritual ``resolve_writer`` / ``resolve_runtime_state`` use.

    ``required=True`` (fail-loud, e.g. ``think.llm.invoke``): a missing
    adapter raises ``TypeError`` naming the node.
    ``required=False`` (fail-soft, e.g. ``reflect.memory_extract``): a
    missing adapter returns ``None`` so the call site's own passthrough
    branch (missing adapter or no ``complete`` method) stays load-bearing.
    """
    runtime = getattr(context, "runtime", None)
    adapter = getattr(runtime, "adapter", None) if runtime is not None else None
    if adapter is None and runtime is not None and hasattr(runtime, "get"):
        adapter = runtime.get("adapter")
    if adapter is None and required:
        raise TypeError(f"{node}: 'adapter' must be supplied via context.runtime")
    return adapter


def resolve_runtime_brain(*, context: NodeContext, node: str, required: bool = False) -> Any:
    """Pull the brain (capability host) from the whitelisted kernel runtime carrier.

    Two-shape probe (attribute first, then mapping-style ``.get``) — the
    same ritual ``resolve_writer`` / ``resolve_runtime_state`` /
    ``resolve_runtime_adapter`` use.

    ``required=True`` (fail-loud): a missing brain raises ``TypeError``
    naming the node.
    ``required=False`` (fail-soft, default — all current brain consumers
    treat ``None`` as absent): a missing brain returns ``None`` so the
    call site's own capability-absence branch stays load-bearing.
    """
    runtime = getattr(context, "runtime", None)
    brain = getattr(runtime, "brain", None) if runtime is not None else None
    if brain is None and runtime is not None and hasattr(runtime, "get"):
        brain = runtime.get("brain")
    if brain is None and required:
        raise TypeError(f"{node}: 'brain' must be supplied via context.runtime")
    return brain
