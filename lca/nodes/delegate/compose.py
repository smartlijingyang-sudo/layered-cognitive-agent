"""delegate.compose — typed fan-out boundary (ADR-0228 D5).

External reference (borrowed / rejected): the existing
``AGENT_FANOUT`` strategy at ``lca/framework/graph/strategies/
agent_fanout_strategy.py`` (ADR-0228 §L19) is the runtime substrate —
this node adds the typed-port contract that the strategy lacked.
Hermes-agent's ``delegate_task`` (history/2026-08/hermes-agent-
pluginization §"工具") is rejected because it grants sub-agents write
access to agent-local state; LCA enforces AGENTS.md §3 C5 capability
monotonicity via ``CapabilityGrantExceededError`` when the parent
grant lacks the ``"delegate"`` capability. The ``idempotency_key``
field (ADR-0228 §Decision 5 + AGENTS.md §3 C9) makes retry safe.

Reads a Decision port and emits a tuple of :class:`DelegationRequest`,
one per declared target. The kernel runs them via the existing
``AGENT_FANOUT`` strategy with capability-monotonicity check (C5);
``idempotency_key`` makes retry safe (C9).

The executor treats the ``capability_grant`` port as duck-typed: any
object exposing a ``capabilities`` collection is accepted, and the
``"delegate"`` membership is the C5 authority check. This keeps the
port contract local to the delegate subgraph instead of forcing the
unrelated :class:`lca.contracts.protocols.act.command.envelope.CapabilityGrant`
(single-capability field) to grow a multi-capability shape.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

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
from lca.contracts.mechanisms.composition.composition import (
    CapabilityGrantExceededError,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.delegation import DelegationRequest
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# C5: capability key required on the parent's grant for fan-out.
DELEGATE_CAPABILITY = "delegate"

# C9: timeout_ms is a per-request budget the kernel translates to a
# deadline; the constant lives here so the typed contract and the
# executor agree without re-importing the strategy module.
DEFAULT_TIMEOUT_MS = 30_000


@dataclass(frozen=True, slots=True)
class DelegateComposeExecutor:
    """delegate.compose: Decision + capability_grant → tuple[DelegationRequest]."""

    semantic_name: str = "delegate.compose"
    region: str = "region:delegate"
    declared_inputs: tuple[PortName, ...] = ("decision", "capability_grant")
    declared_outputs: tuple[PortName, ...] = ("delegation_request",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Resolve decision + grant, fan-out into typed requests.

        ``decision.delegate_to`` is the typed port contract: a list of
        agent ``semantic_name`` strings, or the literal ``"*"`` for a
        kernel-broadcast fan-out. ``capability_grant`` exposes a
        ``capabilities`` collection; ``DELEGATE_CAPABILITY`` must be a
        member (C5 monotonicity).
        """
        del context
        decision = _resolve_port("decision", input=input)
        grant = _resolve_port("capability_grant", input=input)
        _enforce_delegate_capability(grant)
        targets = _targets_from_decision(decision)
        requests = tuple(
            DelegationRequest(
                delegate_to=target,
                payload={
                    "decision_id": getattr(decision, "decision_id", ""),
                    "objective": _objective_from_decision(decision),
                },
                timeout_ms=DEFAULT_TIMEOUT_MS,
                idempotency_key=f"{getattr(decision, 'decision_id', '')}:{target}",
            )
            for target in targets
        )
        return NodeOutput(port_values={"delegation_request": requests})


def _resolve_port(name: str, *, input: NodeInput) -> Any:
    """Pull a declared port from ``input.port_values``; missing → TypeError."""
    value = input.port_values.get(name)
    if value is None:
        raise TypeError(f"delegate.compose: '{name}' port must be supplied via input.port_values")
    return value


def _targets_from_decision(decision: Any) -> tuple[str, ...]:
    """Read the ``delegate_to`` port contract; accept list[str] or ``"*"``.

    Anything else fails loud at the typed-boundary seam — the typed
    contract is the spec, not a duck-type best-effort.
    """
    targets_attr = getattr(decision, "delegate_to", None)
    if isinstance(targets_attr, str):
        if targets_attr == "*":
            return ("*",)
        raise TypeError(
            f"delegate.compose: 'decision.delegate_to' string must be '*'; got {targets_attr!r}"
        )
    if isinstance(targets_attr, (list, tuple)):
        for index, item in enumerate(targets_attr):
            if not isinstance(item, str):
                raise TypeError(
                    "delegate.compose: 'decision.delegate_to' must be list[str]; "
                    f"item[{index}] is {type(item).__name__}"
                )
        return tuple(targets_attr)
    raise TypeError(
        "delegate.compose: 'decision.delegate_to' must be list[str] or '*'; "
        f"got {type(targets_attr).__name__}"
    )


def _objective_from_decision(decision: Any) -> str:
    """Extract the fan-out objective from the decision payload.

    Looks for ``action_payload['objective']`` first (matches the
    ``plan.compose`` / ``plan.revise`` shape); falls back to the
    legacy ``rationale`` field so existing decide-emit producers keep
    working until plan store is wired in.
    """
    action_payload = getattr(decision, "action_payload", None)
    if isinstance(action_payload, dict):
        objective = action_payload.get("objective")
        if isinstance(objective, str):
            return objective
    rationale = getattr(decision, "rationale", "")
    if isinstance(rationale, str):
        return rationale
    return ""


def _grant_capabilities(grant: Any) -> Iterable[str]:
    """Return the capability keys declared on the grant port object."""
    capabilities = getattr(grant, "capabilities", None)
    if capabilities is None:
        raise TypeError(
            "delegate.compose: 'capability_grant' port must expose a 'capabilities' collection"
        )
    return capabilities


def _enforce_delegate_capability(grant: Any) -> None:
    """C5 check: parent's grant must include the ``delegate`` capability."""
    granted = tuple(_grant_capabilities(grant))
    if DELEGATE_CAPABILITY not in granted:
        raise CapabilityGrantExceededError(
            f"delegate.compose: parent grant missing '{DELEGATE_CAPABILITY}' "
            "capability required for fan-out",
            granted=granted,
            required=(DELEGATE_CAPABILITY,),
        )


@plugin(
    id="lca.nodes.delegate.compose",
    Config=None,
    provides=("region:delegate::delegate.compose",),
    requires=("decision", "capability_grant"),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=("network",),
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
                "phase_delegate_compose.checked",
                "phase_delegate_compose.served",
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
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = DelegateComposeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = [
    "DEFAULT_TIMEOUT_MS",
    "DELEGATE_CAPABILITY",
    "DelegateComposeExecutor",
    "setup",
]
