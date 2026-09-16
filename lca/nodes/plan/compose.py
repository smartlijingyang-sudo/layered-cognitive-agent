"""region.plan.compose — seed the typed plan store on first turn (ADR-0228 §Decision 3).

External reference (borrowed / rejected): BabyAGI's todo seeding loop and
AutoGPT's ``task_creation_agent`` (ADR-0228 §L17) shape the entry-derive
path. Hermes-agent's ``delegate_task`` (history/2026-08/hermes-agent-
pluginization/hermes-agent-research.md §"工具") is rejected because it
mutates agent-local state directly; LCA forbids that under AGENTS.md §3
C4 Reducer single-writer — the executor emits a typed ``TaskList`` port
and lets the reducer fold it onto ``AgentState.task_list``.

Per ADR-0228 D3: reads ``state.task_list`` (or seeds an empty list), the
latest ``decision`` port, and ``observation`` for context. Emits a new
``TaskList`` typed port. Brain reads; the reducer folds it back onto
``AgentState.task_list`` (single writer, AGENTS.md §3 C4).

Seeding rule (mirrors the brief):

- If ``state.task_list.entries`` is empty (first entry into plan region),
  seed one ``TaskEntry`` derived from the inbound ``decision`` —
  ``task_id`` is a stable short hash of ``objective + current_step``;
  ``objective`` defaults to ``decision.rationale`` (Decision has no
  ``action_payload`` field in this codebase; ``rationale`` is the
  closest typed carrier for "what the agent decided to do and why").
- If ``entries`` is non-empty, do NOT re-seed (idempotent — the same
  decision fed twice must not duplicate entries). The executor still
  bumps ``TaskList.revision`` so replans are observable to consumers.

Boundary discipline:

- AGENTS.md §3 C4 — Reducer single write: this node does not mutate
  ``AgentState.task_list``. It only emits a typed ``task_list`` port;
  the reducer folds it back onto ``AgentState``.
- AGENTS.md §3 C11 — Event closed set: no new spine EP is introduced.
  The compose step is a pure port-to-port transform.
- AGENTS.md §3 C13 — Typed Contract: ``TaskList`` / ``TaskEntry`` are
  Pydantic ``frozen=True`` + ``extra="forbid"``.

Canonical node shape (ADR-0228 §Decision 2): hand-written
``@dataclass(frozen=True, slots=True)`` + ``@plugin(...)`` carrier, no
decorator magic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

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
from lca.contracts.models.cognition.task import (
    TaskEntry,
    TaskId,
    TaskList,
)
from lca.contracts.models.core.execution.decision import Decision, Observation
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


def _short_task_id(seed: str) -> TaskId:
    """Stable, short, content-addressed task id.

    First 12 hex chars of ``sha256(seed)`` — enough to be collision-
    resistant within a single run's plan (small ``entries`` count) and
    short enough to be human-readable in logs / journal.
    """
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return TaskId(digest[:12])


def _derive_objective(decision: Decision) -> str:
    """Resolve the seed ``objective`` text from the inbound Decision.

    Decision has no ``action_payload.objective`` field in this codebase;
    ``rationale`` is the typed carrier of "what the agent decided to do
    and why" and is the closest analogue. ``response_text`` is the
    fallback when ``rationale`` is empty.
    """
    if decision.rationale:
        return decision.rationale
    if decision.response_text:
        return decision.response_text
    return f"{decision.action_type}:{decision.decision_id}"


def _compose_entries(
    current: tuple[TaskEntry, ...],
    decision: Decision,
    observation: Observation | None,
    *,
    current_step: int,
) -> tuple[TaskEntry, ...]:
    """Return the next entry tuple.

    Empty ``current`` → seed exactly one entry from ``decision``;
    non-empty ``current`` → idempotent (the inbound decision does not
    duplicate entries). ``observation`` is currently unused; it is kept
    in the signature so future revisions can fold observation-derived
    completion signals without changing the call site (C6).
    """
    del observation  # unused on first landing; reserved for future fold
    if current:
        return current
    objective = _derive_objective(decision)
    seed = f"{objective}|{current_step}|{decision.decision_id}"
    return (
        TaskEntry(
            task_id=_short_task_id(seed),
            objective=objective,
            status="pending",
            created_at_turn=current_step,
        ),
    )


def _extract_task_list(state: object) -> TaskList:
    """Resolve the current ``TaskList`` from the state port value.

    Accepts a bare ``TaskList`` (typed shortcut projection) or an
    ``AgentState`` carrying the ``task_list`` field added by ADR-0228.
    Missing / unset → empty list so the node always produces a valid
    typed artifact (C6 minimization).
    """
    if isinstance(state, TaskList):
        return state
    candidate: object = getattr(state, "task_list", None)
    if isinstance(candidate, TaskList):
        return candidate
    return TaskList()


@dataclass(frozen=True, slots=True)
class PlanComposeExecutor:
    """plan node: seed ``TaskList`` on first entry; bump revision otherwise.

    The executor carries no per-instance state; two instances
    constructed in the same process must agree on the same inputs
    (idempotency invariant used by tests).
    """

    semantic_name: str = "plan.compose"
    region: str = "plan"
    declared_inputs: tuple[PortName, ...] = ("state", "decision", "observation")
    declared_outputs: tuple[PortName, ...] = ("task_list",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """plan 子图节点入口。

        inputs 端口(yaml):state, decision, observation
        outputs 端口(yaml):task_list
        """
        del context  # unused: pure function of input ports
        state = input.port_values.get("state")
        decision_value = input.port_values.get("decision")
        observation_value = input.port_values.get("observation")
        if not isinstance(decision_value, Decision):
            raise TypeError(
                "plan.compose expects Decision on port 'decision',"
                f" got {type(decision_value).__name__}"
            )
        if observation_value is not None and not isinstance(observation_value, Observation):
            raise TypeError(
                "plan.compose expects Observation on port 'observation',"
                f" got {type(observation_value).__name__}"
            )
        current = _extract_task_list(state)
        current_step = _extract_current_step(state)
        next_entries = _compose_entries(
            current.entries,
            decision_value,
            observation_value,
            current_step=current_step,
        )
        return NodeOutput(
            port_values={
                "task_list": TaskList(
                    entries=next_entries,
                    revision=current.revision + 1,
                ),
            },
        )


def _extract_current_step(state: object) -> int:
    """Pull ``state.step`` when state is an ``AgentState``; else 0.

    ``AgentState.step`` is the cognitive step counter (no separate
    ``turn`` field exists in this codebase); it serves as the
    ``created_at_turn`` anchor for seeded entries.
    """
    return int(getattr(state, "step", 0) or 0)


@plugin(
    id="lca.nodes.plan.compose",
    Config=None,
    provides=("plan::plan.compose",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
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
                "phase_plan_compose.checked",
                "phase_plan_compose.served",
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
    executor = PlanComposeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = [
    "PlanComposeExecutor",
    "setup",
]
