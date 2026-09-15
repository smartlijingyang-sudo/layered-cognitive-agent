"""``@graph_node`` decorator — typed-boundary DSL for declarative nodes.

ADR-0227 §Decision: this decorator generalizes the
``@dataclass(slots=True)`` ``NodeExecutor`` + ``@plugin(...)`` setup pair
that lived inline in
:mod:`lca.nodes.concept.context_compose.collect.collect` and
:mod:`lca.plugins.think.history_assemble.execute` (PR2). Plugin authors
write one function definition per node; the decorator produces the
identical artifact the hand-written pair produces today.

Usage::

    @graph_node(
        id="think.history.assemble",
        region="think",
        inputs=("state", "writer"),
        outputs=("model_visible_request",),
        terminal=lambda output, state: ("continue", state),
    )
    async def history_assemble(*, state, writer) -> ModelVisibleRequest:
        ...

The decorator returns a ``@plugin(...)`` carrier; the user fn's bound
executor lives at ``<carrier>.setup`` and the cordis registration entry
point at ``<carrier>.setup.setup(ctx, config=None)``, which registers
under ``f"{region}::{id}"``. To obtain the executor dataclass for
introspection, call ``<carrier>.__wrapped__()`` (returns a fresh
instance) or import the auto-named ``<Fn>Executor`` from the same
module where ``@graph_node`` was applied.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

#: Six-phase closed set (ADR-0227 §3). ``region`` must be one of these.
ALLOWED_REGIONS: frozenset[str] = frozenset(
    {"perceive", "think", "act", "remember", "reflect", "stop"}
)

#: ``terminal_predicate`` verdict strings accepted in ``NodeOutput.next_hint``.
TERMINAL_CONTINUE = "continue"
TERMINAL_EXIT = "exit"

TerminalPredicate: TypeAlias = Callable[[Mapping[str, Any], AgentState], tuple[str, AgentState]]


def _resolve_port(
    *,
    name: str,
    input: NodeInput,
    context: NodeContext,
) -> Any:
    """Read a declared port from ``input.port_values``, falling back to ``context.runtime``.

    Mirrors ``lca/plugins/think/history_assemble/execute.py:62-79`` and
    ``lca/plugins/concept/context_compose/collect.py:55-65``.
    Missing on both → ``TypeError`` (typed-boundary守门人).
    """
    value = input.port_values.get(name)
    if value is None:
        value = context.runtime.get(name) if hasattr(context, "runtime") else None
    if value is None:
        raise TypeError(
            f"@graph_node: '{name}' port must be supplied via input.port_values or context.runtime"
        )
    return value


def _pack_outputs(
    *,
    declared_outputs: tuple[PortName, ...],
    return_value: Any,
) -> dict[PortName, Any]:
    """Translate the user fn's return value into ``NodeOutput.port_values``.

    - ``dict`` whose keys match all ``declared_outputs`` → used directly.
    - ``dict`` with keys that don't match → wrapped under the single
      declared output when ``len(declared_outputs) == 1`` (lets user fns
      return richer typed objects like ``Decision`` without unpacking);
      ``TypeError`` otherwise.
    - ``tuple`` / ``list`` → zipped with ``declared_outputs`` in order.
    - scalar → wrapped as a single-element mapping under the only declared output.
    """
    if isinstance(return_value, Mapping):
        if set(return_value) == set(declared_outputs):
            return dict(return_value)
        if len(declared_outputs) == 1:
            return {declared_outputs[0]: return_value}
        raise TypeError(
            f"@graph_node: declared_outputs={declared_outputs} but returned "
            f"dict with keys {sorted(return_value)} (no key overlap); "
            "return a tuple aligned with declared outputs or a dict keyed "
            "by declared output names"
        )
    if isinstance(return_value, (tuple, list)):
        if len(return_value) != len(declared_outputs):
            raise TypeError(
                f"@graph_node: declared_outputs={declared_outputs} but returned "
                f"{len(return_value)} values (positional return requires "
                "declared_outputs.length == return tuple length)"
            )
        return dict(zip(declared_outputs, return_value, strict=True))
    if len(declared_outputs) == 1:
        return {declared_outputs[0]: return_value}
    raise TypeError(
        f"@graph_node: declared_outputs={declared_outputs} but returned scalar; "
        "return a dict keyed by declared outputs or a tuple aligned with them"
    )


def _build_executor_dataclass(
    *,
    dataclass_name: str,
    semantic_name: str,
    region: str,
    declared_inputs: tuple[PortName, ...],
    declared_outputs: tuple[PortName, ...],
    user_fn: Callable[..., Awaitable[Any]],
    terminal: TerminalPredicate | None,
) -> type:
    """Build a frozen ``@dataclass(slots=True)`` executor for the bound user fn.

    The executor carries the closed-set surface (semantic_name / region /
    declared_inputs / declared_outputs / terminal_predicate) so PR2
    readers (audit-plugin-shape, plan compilation) see the same shape the
    hand-written ``ContextLinesCollectExecutor`` /
    ``HistoryAssembleExecutor`` expose.
    """
    # Bind the parameter values into local names that do not collide with
    # the dataclass field names — Python evaluates the default expressions
    # in a class body where the field names are already bound to the
    # ``dataclasses.Field`` descriptors.
    _semantic_name = semantic_name
    _region = region
    _declared_inputs = declared_inputs
    _declared_outputs = declared_outputs
    _terminal = terminal
    _user_fn = user_fn

    @dataclass(frozen=True, slots=True)
    class _Executor:
        semantic_name: str = _semantic_name
        region: str = _region
        declared_inputs: tuple[PortName, ...] = _declared_inputs
        declared_outputs: tuple[PortName, ...] = _declared_outputs
        terminal_predicate: TerminalPredicate | None = _terminal

        async def node_execute(
            self,
            context: NodeContext,
            input: NodeInput,
        ) -> NodeOutput:
            """Resolve declared ports, invoke the user fn, evaluate terminal_predicate."""
            kwargs: dict[str, Any] = {
                name: _resolve_port(name=name, input=input, context=context)
                for name in _declared_inputs
            }
            return_value = await _user_fn(**kwargs)
            port_values = _pack_outputs(
                declared_outputs=_declared_outputs,
                return_value=return_value,
            )
            next_hint: str | None = None
            if _terminal is not None:
                state_value = kwargs.get("state")
                verdict, _state = _terminal(port_values, state_value)  # type: ignore[arg-type]
                if verdict not in (TERMINAL_CONTINUE, TERMINAL_EXIT):
                    raise ValueError(
                        f"@graph_node: terminal_predicate returned {verdict!r}; "
                        f"expected one of {TERMINAL_CONTINUE!r} / {TERMINAL_EXIT!r}"
                    )
                next_hint = verdict
            return NodeOutput(port_values=port_values, next_hint=next_hint)

    _Executor.__name__ = dataclass_name
    _Executor.__qualname__ = dataclass_name
    return _Executor


def graph_node(
    *,
    id: str,
    region: str,
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
    terminal: TerminalPredicate | None = None,
    effects: str = "none",
    layer: str = "L2",
) -> Callable[[Callable[..., Awaitable[Any]]], Any]:
    """Wrap an async fn as a ``NodeExecutor``-shaped ``@plugin(...)`` carrier.

    See module docstring + ADR-0227 §Decision.

    Returns a wrapper exposing the bound ``NodeExecutor`` dataclass shape
    (``semantic_name`` / ``region`` / ``declared_inputs`` /
    ``declared_outputs``) as instance attributes, with the underlying
    cordis ``Plugin`` carrier at ``<decorated>.setup``. Registration entry
    point: ``<decorated>.setup.setup(ctx, config=None)``, which
    constructs a fresh executor instance and calls
    ``ctx.provide(f"{region}::{id}", executor)`` — identical to
    ``lca/plugins/concept/context_compose/collect.py:103-108``. The
    cordis carrier carries the canonical ``PluginContract`` + ``OwnershipDeclaration``
    so PR2 audit / plan readers find the same surface.
    """
    if region not in ALLOWED_REGIONS:
        raise ValueError(
            f"@graph_node region={region!r} not in six-phase closed set; "
            f"allowed: {sorted(ALLOWED_REGIONS)}"
        )
    if not id or not isinstance(id, str):
        raise ValueError("@graph_node requires a non-empty str id=")

    declared_inputs: tuple[PortName, ...] = tuple(inputs)
    declared_outputs: tuple[PortName, ...] = tuple(outputs)

    def _decorate(user_fn: Callable[..., Awaitable[Any]]) -> Any:
        if not callable(user_fn):
            raise TypeError(f"@graph_node target must be callable, got {type(user_fn).__name__}")

        executor_cls = _build_executor_dataclass(
            dataclass_name=f"{user_fn.__name__.title().replace('_', '')}Executor",
            semantic_name=id,
            region=region,
            declared_inputs=declared_inputs,
            declared_outputs=declared_outputs,
            user_fn=user_fn,
            terminal=terminal,
        )

        @plugin(
            id=f"phase.{region}.{id}",
            Config=None,
            provides=(f"{region}::{id}",),
            requires=(),
            layer=layer,
            kind=PluginKind.PRIMITIVE,
            effects=effects,
            contract=PluginContract(
                identity=PluginIdentity(version="v1"),
                architecture=ArchitectureContract(
                    group=FunctionalGroup.G7_EXECUTION,
                    control_slots=(ControlSlot.OBSERVE_WILDCARD,),
                ),
                lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
                authority=AuthorityContract(grants=("plugin.serve",)),
                observability=EvidenceContract(
                    descriptors=(
                        f"phase_{region}_{id.replace('.', '_')}.checked",
                        f"phase_{region}_{id.replace('.', '_')}.served",
                    )
                ),
            ),
            ownership=OwnershipDeclaration(
                reads=("plugin.serve",),
                emits=("plugin.served",),
                state_mutation="forbidden",
            ),
        )
        async def setup(ctx: PluginContext, config=None) -> None:
            """Composite-key 注册:``{region}::{semantic_name}``."""
            del config
            executor = executor_cls()
            composite_key = f"{executor.region}::{executor.semantic_name}"
            ctx.provide(composite_key, executor)

        # Bind a fresh executor instance and lift its dataclass attributes
        # onto the wrapper so callers can introspect the surface
        # (``no_op.semantic_name`` etc.) without going through ``ctx.provide``.
        # The wrapper additionally exposes the cordis Plugin carrier as
        # ``<decorated>.setup`` so the registration access pattern
        # ``<decorated>.setup.setup(ctx, config=None)`` mirrors the
        # hand-written ``module.setup.setup(ctx, config=None)`` access
        # (where the module-level variable is named ``setup``).
        sample = executor_cls()

        wrapper_cls = type(
            user_fn.__name__,
            (),
            {
                "__doc__": user_fn.__doc__,
            },
        )
        wrapper = wrapper_cls()
        wrapper.setup = setup  # type: ignore[attr-defined]
        wrapper.semantic_name = sample.semantic_name  # type: ignore[attr-defined]
        wrapper.region = sample.region  # type: ignore[attr-defined]
        wrapper.declared_inputs = sample.declared_inputs  # type: ignore[attr-defined]
        wrapper.declared_outputs = sample.declared_outputs  # type: ignore[attr-defined]
        wrapper.terminal_predicate = sample.terminal_predicate  # type: ignore[attr-defined]
        wrapper.__wrapped__ = executor_cls  # type: ignore[attr-defined]
        wrapper.__executor_cls__ = executor_cls  # type: ignore[attr-defined]
        return wrapper

    return _decorate


__all__ = [
    "ALLOWED_REGIONS",
    "TERMINAL_CONTINUE",
    "TERMINAL_EXIT",
    "graph_node",
]
