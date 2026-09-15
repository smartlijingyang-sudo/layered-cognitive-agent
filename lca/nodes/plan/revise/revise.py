"""region.plan.revise — replan based on Reflection (ADR-0228 §Decision 3).

External reference (borrowed / rejected): BabyAGI's replan task-priority
loop (ADR-0228 §L17) shapes the ``replan_requested`` + ``blocked_tasks``
diffing. Hermes-agent's ``_LoopState`` aggregate (history/2026-08/
hermes-agent-loop §"What we reject") is rejected because mixing 30+
fields into one mutable aggregate violates AGENTS.md §3 C13 (typed
Contract per cross-boundary payload) and C4 (Reducer single-writer);
this node keeps ``TaskList`` as the typed SSOT and emits a new
immutable revision.

Per ADR-0228 D3: reads ``state.task_list`` + ``reflection.replan_requested``
+ ``reflection.blocked_tasks`` and emits a revised ``TaskList`` with a
bumped revision. Entries whose ``depends_on`` references an entry that
is not ``status == "completed"`` are stamped ``status = "blocked"``.
Already-completed entries are never re-stamped.

Boundary discipline:

- AGENTS.md §3 C4 — Reducer single write: this node does not mutate
  ``AgentState.task_list``. It only emits a typed ``task_list`` port;
  the reducer folds it back onto ``AgentState``.
- AGENTS.md §3 C11 — Event closed set: no new spine EP is introduced.
  The revise step is a pure port-to-port transform.
- AGENTS.md §3 C13 — Typed Contract: ``Reflection`` / ``TaskList`` /
  ``TaskEntry`` are Pydantic ``frozen=True`` + ``extra="forbid"``.
- AGENTS.md §3 C6 — Minimization: primitives default to no-op; the
  pure-function helper ``_revise_entries`` is reusable by plan.compose
  for revision bookkeeping.

Canonical node shape (ADR-0228 §Decision 2): hand-written
``@dataclass(frozen=True, slots=True)`` + ``@plugin(...)`` carrier, no
decorator magic.
"""

from __future__ import annotations

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
    Reflection,
    TaskEntry,
    TaskList,
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _revise_entries(
    entries: tuple[TaskEntry, ...],
    reflection: Reflection,
    *,
    completed_set: frozenset[object] | None = None,
) -> tuple[TaskEntry, ...]:
    """Return the revised entry tuple.

    Identity is stable: existing ``task_id`` values are preserved and
    the helper never deletes entries. ``reflection.blocked_tasks`` is
    the highest-priority signal (it wins over ``depends_on`` and the
    replan reset). When ``replan_requested`` is True, every non-completed
    entry is reset to ``"pending"`` — except those still blocked by
    ``depends_on`` (the replan is no excuse to skip an unmet dependency).
    """
    if completed_set is None:
        completed_set = frozenset(entry.task_id for entry in entries if entry.status == "completed")
    blocked_set = frozenset(reflection.blocked_tasks)
    next_entries: list[TaskEntry] = []
    for entry in entries:
        if entry.task_id in blocked_set:
            next_entries.append(entry.model_copy(update={"status": "blocked"}))
            continue
        if entry.status != "completed" and entry.depends_on:
            unmet = any(dep not in completed_set for dep in entry.depends_on)
            if unmet:
                next_entries.append(entry.model_copy(update={"status": "blocked"}))
                continue
        if entry.status != "completed" and reflection.replan_requested:
            # TaskList.revision (not per-entry revision) is the
            # monotonic source; the caller bumps it once on the
            # enclosing TaskList.
            next_entries.append(entry.model_copy(update={"status": "pending"}))
            continue
        next_entries.append(entry)
    return tuple(next_entries)


@dataclass(frozen=True, slots=True)
class PlanReviseExecutor:
    """plan node: emit a revised ``TaskList`` based on Reflection.

    The executor carries no per-instance state; two instances
    constructed in the same process must agree on the same inputs
    (idempotency invariant used by tests).
    """

    semantic_name: str = "plan.revise"
    region: str = "region:plan"
    declared_inputs: tuple[PortName, ...] = ("state", "reflection")
    declared_outputs: tuple[PortName, ...] = ("task_list",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """plan 子图节点入口。

        inputs 端口(yaml):state, reflection
        outputs 端口(yaml):task_list
        """
        del context  # unused: pure function of input ports
        state = input.port_values.get("state")
        reflection_value = input.port_values.get("reflection")
        if not isinstance(reflection_value, Reflection):
            raise TypeError(
                "plan.revise expects Reflection on port 'reflection',"
                f" got {type(reflection_value).__name__}"
            )
        current = _extract_task_list(state)
        next_entries = _revise_entries(current.entries, reflection_value)
        # C6 minimization: when there is nothing to revise (empty list +
        # no replan / blocked signal) the executor returns identity so the
        # reducer does not need to fold a no-op delta. Any active signal
        # bumps the revision to make the replan observable to consumers.
        is_no_op = (
            not current.entries
            and not reflection_value.replan_requested
            and not reflection_value.blocked_tasks
        )
        next_revision = current.revision if is_no_op else current.revision + 1
        return NodeOutput(
            port_values={
                "task_list": TaskList(
                    entries=next_entries,
                    revision=next_revision,
                ),
            },
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


@plugin(
    id="lca.nodes.plan.revise",
    Config=None,
    provides=("region:plan::plan.revise",),
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
                "phase_plan_revise.checked",
                "phase_plan_revise.served",
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
    executor = PlanReviseExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = [
    "PlanReviseExecutor",
    "setup",
]
