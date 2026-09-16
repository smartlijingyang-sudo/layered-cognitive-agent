"""End-to-end safety net for ``bundles/act/act_subgraph.yaml``.

The final review (PR-3.8.4 + PR-3.8.5 + fix1) found three structural
defects in ``bundles/act/act_subgraph.yaml`` that the existing unit
+ integration test suite did not catch:

1. ``act.fanout`` was unreachable — the bundle had no
   ``act.envelope → act.fanout`` or ``act.fanout → act.dispatch`` edges
   (the fan-out node was defined but never wired).
2. The ``act.join → act.observe`` edge carried TWO ``when:`` keys —
   PyYAML's ``safe_load`` keeps the last duplicate, silently dropping
   the ``routing.next_hint == "join_1to1"`` predicate map. The N:N
   reject path (``join_rejects_parallel_in_v1``) routed to
   ``act.observe`` anyway.
3. The ``act.envelope → act.dispatch`` direct edge was a leftover from
   the baseline that bypasses ``act.fanout`` and was made redundant by
   the fix.

The existing ``tests/integration/test_act_dispatch_join_observe_e2e.py``
wires its plan inline (``_outer_plan`` builds the spec dict directly)
and never reads ``bundles/act/act_subgraph.yaml`` — so the broken
bundle escaped detection in two review rounds. This module closes
that gap.

What this test does (matches the production path used by
:func:`lca_kernel.boot.plan_validation.validate_profile_plans`):

- Loads ``bundles/act/act_subgraph.yaml`` with ``yaml.safe_load`` and
  asserts the raw yaml has **no duplicate ``when:`` keys on any edge**
  (catches Defect 1b at the syntax layer).
- Lifts the bundle via :func:`_lift_graph_spec_inner` with the same
  entry-fallback :func:`lca_kernel.boot.plan_validation._apply_entry_fallback`
  applies to inner subgraph plans (the production path).
- Runs the kernel's reachability BFS
  (:func:`lca_kernel.boot.plan_validation._check_reachability` logic) on
  the lifted :class:`Plan` and asserts every declared node — including
  ``act.fanout`` — is reachable from the plan entry. Catches Defect 1a
  + 1c.
- Asserts the lifted predicate on ``act.fanout → act.dispatch`` is the
  ``routing.next_hint == "fanout_1to1"`` :class:`Predicate` (not
  ``None``/``True``). Catches Defect 1a.
- Asserts the lifted predicate on ``act.join → act.observe`` is the
  ``routing.next_hint == "join_1to1"`` :class:`Predicate` (not
  ``True``). Catches Defect 1b.
- Asserts there is **no** direct ``act.envelope → act.dispatch`` edge
  on the lifted plan. Catches Defect 1c.

Finally, runs the lifted plan through :class:`PlanInterpreter` with
real executors wired for every act node plus the real
:class:`EffectExecuteExecutor` for the inner
``act.dispatch → effect.execute`` subgraph — the full
``act.validate → act.authorize → act.envelope → act.fanout →
act.dispatch → act.join → act.observe`` chain. Confirms every node is
visited and the receipt round-trip closes end-to-end.

Per AGENTS.md §3 C10 + C13, this test exercises the typed-port wiring
that production depends on; the inner ``effect.execute`` is the unique
effect entry, and only the *runtime* ``effect_gateway`` capability is
stubbed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.act.command.envelope import (
    CommandEnvelope,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext as LegacyNodeContext,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeExecutor,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeInput as LegacyNodeInput,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeOutput as LegacyNodeOutput,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.plan import Plan
from lca.contracts.protocols.graph.predicate import Predicate
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lifter import (
    _lift_graph_spec_inner,
    validate_predicates,
)
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.strategies.node_executor_strategy import (
    NodeExecutorStrategy,
)
from lca.framework.graph.strategies.subgraph_strategy import SubgraphStrategy
from lca.framework.graph.strategy_registry import StrategyRegistry
from lca.nodes.act.authorize.authorize import ActAuthorizeExecutor
from lca.nodes.act.envelope.envelope import ActEnvelopeExecutor
from lca.nodes.act.fanout import ActFanoutExecutor
from lca.nodes.act.join import ActJoinExecutor
from lca.nodes.act.observe.observe import ActObserveExecutor
from lca.nodes.act.validate.validate import ActValidateExecutor
from lca.nodes.concept.effect.execute import EffectExecuteExecutor
from lca.nodes.intervene.approve_gate import ApproveGateExecutor
from lca.nodes.intervene.resume import ResumeExecutor

BUNDLE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "bundles" / "act" / "act_subgraph.yaml"
)


# ── Bundle helpers (mirror production validation path) ─────────────────


def _apply_entry_fallback(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Mirror :func:`lca_kernel.boot.plan_validation._apply_entry_fallback`.

    Production lifts inner subgraph plans through the same helper to
    inject ``entry: True`` on the first node when no node marks itself
    as entry. This test re-uses the production logic so a future
    change to the helper propagates here automatically.
    """
    spec = dict(mapping)
    nodes = list(spec.get("nodes") or ())
    if nodes and not any(isinstance(n, dict) and n.get("entry") for n in nodes):
        nodes[0] = {**nodes[0], "entry": True}
        spec["nodes"] = nodes
    return spec


def _load_bundle_raw() -> dict[str, Any]:
    """Load the bundle yaml as a raw mapping."""
    raw = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), (
        f"{BUNDLE_PATH}: top-level must be a mapping, got {type(raw).__name__}"
    )
    return raw


def _lift_bundle() -> Plan:
    """Lift the bundle through the production inner-subgraph path.

    Uses :func:`_lift_graph_spec_inner` (the inner-subgraph lifter,
    same one :func:`lca_kernel.boot.plan_validation._lift_with_optional_termination`
    uses when ``enforce_termination=False``) plus the entry-fallback
    helper the production validator applies first. Adds
    :func:`validate_predicates` so any future leaf-predicate that
    references an undeclared port also fails here.
    """
    raw = _load_bundle_raw()
    spec = _apply_entry_fallback(raw)
    plan = _lift_graph_spec_inner(spec)
    validate_predicates(plan)
    return plan


def _reachability_check(plan: Plan) -> set[str]:
    """BFS from the plan entry, mirroring :func:`_check_reachability`."""
    if not plan.nodes:
        return set()
    entry_id = next((n.id for n in plan.nodes if n.entry), None)
    assert entry_id is not None, "lifted plan must have exactly one entry"
    adj: dict[str, list[str]] = {n.id: [] for n in plan.nodes}
    for edge in plan.edges:
        adj.setdefault(edge.source, []).append(edge.target)
    visited: set[str] = {entry_id}
    queue: list[str] = [entry_id]
    while queue:
        cur = queue.pop(0)
        for tgt in adj.get(cur, ()):
            if tgt in visited:
                continue
            visited.add(tgt)
            queue.append(tgt)
    return visited


# ── Section 1: structural assertions on the raw bundle + lifted plan ──


def test_bundle_yaml_has_no_duplicate_when_keys() -> None:
    """YAML 1.1 silently keeps the LAST duplicate key.

    Defect 1b (round-2 review): ``act.join → act.observe`` had two
    ``when:`` keys — a predicate map followed by ``when: true``. The
    predicate map was silently dropped, turning the edge into an
    unconditional route that bypassed the N:N reject path. This
    structural assertion walks the raw yaml text line-by-line so a
    future regression that reintroduces the duplicate is caught at the
    *syntax* layer (before lifting) — the BFS + lifted-predicate
    checks below would also catch it, but the raw-yaml layer is the
    cheapest and most pointed safety net.
    """
    text = BUNDLE_PATH.read_text(encoding="utf-8")
    # Each edge in the bundle is a block under ``edges:``. The
    # ``when:`` key may appear on consecutive lines *within* the same
    # edge (defect shape). We use a small state machine: scan line by
    # line, track when we are inside an edge block (between ``- from:``
    # and the next ``- from:`` or end of list), and detect duplicate
    # ``when:`` lines within the same edge.
    duplicates: list[tuple[int, str, str]] = []
    in_edge = False
    edge_start_line = 0
    seen_when_keys: set[str] = set()
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        # New edge starts with ``- from:`` at 2-space indent.
        if stripped.startswith("- from:"):
            in_edge = True
            edge_start_line = idx
            seen_when_keys = set()
            continue
        if in_edge:
            # Edge block ends when we hit another edge or a non-list
            # sibling key (region, purpose, id, nodes, edges top-level).
            if (
                stripped.startswith("- from:")
                or stripped.startswith("id:")
                or stripped.startswith("region:")
                or stripped.startswith("purpose:")
                or stripped.startswith("nodes:")
                or stripped.startswith("edges:")
                or stripped.startswith("#")
            ):
                in_edge = False
                continue
            if stripped.startswith("when:"):
                if "when" in seen_when_keys:
                    duplicates.append((edge_start_line, "when", stripped))
                seen_when_keys.add("when")
    assert not duplicates, (
        f"{BUNDLE_PATH} contains duplicate `when:` keys on the same edge; "
        "PyYAML silently keeps the last one, dropping the predicate map. "
        f"First duplicate at line {duplicates[0][0]} (edge starts there): "
        f"{duplicates[0][2]!r}"
    )


def test_act_fanout_is_reachable_from_act_validate_in_bundle() -> None:
    """Defect 1a (round-2 review): ``act.fanout`` was unreachable.

    Production's :func:`_check_reachability` rejects plans with
    unreachable nodes at boot time. This test runs the same BFS on
    the *lifted* plan and on the raw yaml adjacency so the wiring is
    verified at both the structural and the typed-port layers.
    """
    raw = _load_bundle_raw()
    raw_node_ids = {n["id"] for n in raw["nodes"]}
    raw_adj: dict[str, list[str]] = {n["id"]: [] for n in raw["nodes"]}
    for edge in raw["edges"]:
        raw_adj.setdefault(edge["from"], []).append(edge["to"])
    raw_visited: set[str] = {"act.validate"}
    queue: list[str] = list(raw_adj.get("act.validate", []))
    while queue:
        cur = queue.pop(0)
        if cur in raw_visited:
            continue
        raw_visited.add(cur)
        queue.extend(raw_adj.get(cur, []))
    assert "act.fanout" in raw_visited, (
        "act.fanout is unreachable from act.validate via raw-yaml "
        "edges. Production kernel rejects this at boot via "
        "_check_reachability. Add 'act.envelope -> act.fanout' and "
        "'act.fanout -> act.dispatch' edges with the fanout_1to1 "
        "predicate (Defect 1a)."
    )
    assert raw_visited == raw_node_ids, (
        f"raw-yaml reachability missed some nodes: unreachable={sorted(raw_node_ids - raw_visited)}"
    )

    plan = _lift_bundle()
    lifted_visited = _reachability_check(plan)
    lifted_node_ids = {n.id for n in plan.nodes}
    assert lifted_visited == lifted_node_ids, (
        f"lifted-plan reachability missed some nodes: "
        f"unreachable={sorted(lifted_node_ids - lifted_visited)}"
    )


def test_act_fanout_to_act_dispatch_carries_fanout_1to1_predicate() -> None:
    """Defect 1a follow-up: the fanout → dispatch edge must carry the
    ``routing.next_hint == "fanout_1to1"`` predicate, not ``True`` /
    ``None`` (unconditional).

    An unconditional edge would defeat the fan-out node: the N:N path
    (when fanout is later extended to emit a list of >1 envelopes)
    would route to dispatch regardless of the routing decision. The
    kernel's :class:`PlanInterpreter` evaluates typed :class:`Predicate`
    objects against the source node's port values; ``True`` /
    ``None`` both mean "always fire".
    """
    plan = _lift_bundle()
    edge = next(
        (e for e in plan.edges if e.source == "act.fanout" and e.target == "act.dispatch"),
        None,
    )
    assert edge is not None, (
        "act.fanout -> act.dispatch edge is missing from the lifted plan. "
        "Defect 1a: fanout is unreachable from the entry. "
        "Add the edge with the routing.next_hint == 'fanout_1to1' predicate."
    )
    assert isinstance(edge.when, Predicate), (
        f"act.fanout -> act.dispatch predicate must be a typed Predicate, "
        f"got {type(edge.when).__name__}. An unconditional edge (None/True) "
        f"bypasses the 1:1 routing decision."
    )
    assert edge.when.kind == "eq", f"expected eq predicate, got kind={edge.when.kind!r}"
    assert edge.when.port is not None and edge.when.port.name == "routing", (
        f"expected port.name='routing', got {edge.when.port!r}"
    )
    assert edge.when.port.field == "next_hint", (
        f"expected port.field='next_hint', got {edge.when.port.field!r}"
    )
    assert edge.when.value == "fanout_1to1", (
        f"expected value='fanout_1to1', got {edge.when.value!r}"
    )


def test_act_join_to_act_observe_carries_join_1to1_predicate_not_true() -> None:
    """Defect 1b (round-2 review): the duplicate ``when:`` keys on
    ``act.join → act.observe`` silently dropped the predicate map.

    After parsing, the edge carried ``when: True`` instead of the
    intended ``routing.next_hint == "join_1to1"`` predicate, so the
    N:N reject path (which emits ``next_hint =
    "join_rejects_parallel_in_v1"``) routed to ``act.observe`` anyway.
    This test pins the lifted predicate to the typed :class:`Predicate`
    shape so a future regression that reintroduces a duplicate ``when:``
    key is caught.
    """
    plan = _lift_bundle()
    edge = next(
        (e for e in plan.edges if e.source == "act.join" and e.target == "act.observe"),
        None,
    )
    assert edge is not None, "act.join -> act.observe edge is missing from the lifted plan."
    assert isinstance(edge.when, Predicate), (
        f"act.join -> act.observe predicate must be a typed Predicate, "
        f"got {type(edge.when).__name__}. If this is None/True, the bundle "
        f"has a duplicate `when:` key (YAML 1.1 silently keeps the last) "
        f"or the predicate map was dropped. Defect 1b."
    )
    assert edge.when.kind == "eq"
    assert edge.when.port is not None and edge.when.port.name == "routing"
    assert edge.when.port.field == "next_hint"
    assert edge.when.value == "join_1to1", (
        f"expected value='join_1to1', got {edge.when.value!r}. "
        f"A True/None value here would let the N:N reject path "
        f"route to act.observe and silently bypass the join barrier."
    )


def test_no_direct_act_envelope_to_act_dispatch_edge() -> None:
    """Defect 1c (round-2 review): the leftover ``act.envelope →
    act.dispatch`` direct edge bypasses ``act.fanout``.

    With the fanout node wired (Defect 1a's fix), this direct edge
    becomes dead/redundant: ``act.envelope`` routes to
    ``act.fanout``, which routes to ``act.dispatch`` on the
    ``fanout_1to1`` predicate. Keeping the direct edge invites a
    future regression where fanout is bypassed.
    """
    plan = _lift_bundle()
    direct = [e for e in plan.edges if e.source == "act.envelope" and e.target == "act.dispatch"]
    assert not direct, (
        f"act.envelope -> act.dispatch direct edge is present "
        f"({len(direct)} occurrence(s)); it bypasses act.fanout and "
        f"is redundant now that envelope -> fanout -> dispatch is "
        f"wired. Defect 1c: remove the direct edge."
    )


def test_lifted_bundle_has_exactly_nine_edges() -> None:
    """Pin the bundle's edge count to catch future silent insertions /
    deletions that would silently bypass the typed-boundary contract.

    Expected edges after PR-1b (ADR-0237):
      - act.validate -> act.authorize
      - act.authorize -> act.approve.gate
      - act.approve.gate -> act.envelope (predicate on approval_routing)
      - intervene.resume -> act.approve.gate (resume cycle)
      - act.envelope -> act.fanout
      - act.fanout -> act.dispatch (predicate)
      - act.dispatch -> act.join
      - act.join -> act.observe (predicate)

    Plus the act.observe chain (PR-3):
      - act.observe -> act.observe.commit_fact
      - act.observe.commit_fact -> act.observe.terminate_decide

    Total: 11 edges. (Asserting == 11 — not "at least" — so any future
    addition is an explicit, reviewed change.)
    """
    plan = _lift_bundle()
    assert len(plan.edges) == 11, (
        f"lifted act.subgraph must have exactly 11 edges, got "
        f"{len(plan.edges)}: "
        f"{[(e.source, e.target) for e in plan.edges]}"
    )


# ── Section 2: kernel-level end-to-end run on the lifted bundle ────────


class _StubEffectGateway:
    """Fake effect gateway; mirrors ``EffectDispatcher.execute`` shape."""

    def __init__(self, invocation_id: str = "inv_subgraph_e2e") -> None:
        self.invocation_id = invocation_id
        self.calls: list[CommandEnvelope] = []

    async def execute(self, envelope: CommandEnvelope, policy: Any) -> dict[str, Any]:
        del policy
        self.calls.append(envelope)
        return {
            "invocation_id": self.invocation_id,
            "idempotency_key": envelope.idempotency_key or self.invocation_id,
            "result": {"success": True, "echo": "ok"},
        }


class _RuntimeScope:
    """Duck-typed capability scope exposing ``effect_gateway``."""

    def __init__(self, gateway: _StubEffectGateway) -> None:
        self._gateway = gateway

    def get(self, key: str) -> Any:
        if key == "effect_gateway":
            return self._gateway
        return None

    def resolve(self, key: str) -> Any:
        return self.get(key)


def _build_runtime_view(gateway: _StubEffectGateway) -> Any:
    """Match the production ``_NodeRuntimeView`` interface."""

    class _View:
        __slots__ = ("_scope", "_state")

        def __init__(self) -> None:
            object.__setattr__(self, "_scope", _RuntimeScope(gateway))
            object.__setattr__(self, "_state", None)

        @property
        def state(self) -> Any:
            return object.__getattribute__(self, "_state")

        def get(self, key: str) -> Any:
            scope = object.__getattribute__(self, "_scope")
            getter = getattr(scope, "get", None) or getattr(scope, "resolve", None)
            return getter(key) if getter else None

        def __getattr__(self, key: str) -> Any:
            scope = object.__getattribute__(self, "_scope")
            getter = getattr(scope, "get", None) or getattr(scope, "resolve", None)
            return getter(key) if getter else None

    return _View()


@dataclass(frozen=True, slots=True)
class _ObserveRecorder:
    """Wraps the real :class:`ActObserveExecutor` and captures the receipt."""

    inner: ActObserveExecutor
    captured: list[EffectReceipt] = field(default_factory=list)

    async def node_execute(
        self,
        context: LegacyNodeContext,
        input: LegacyNodeInput,
    ) -> LegacyNodeOutput:
        output = await self.inner.node_execute(context, input)
        receipt = output.port_values.get("receipt")
        if isinstance(receipt, EffectReceipt):
            object.__setattr__(self, "captured", [*self.captured, receipt])
        return output


def _make_inner_registry(gateway: _StubEffectGateway) -> StrategyRegistry:
    """Inner subgraph registry: only ``effect.execute`` resolves."""
    executors: dict[str, NodeExecutor] = {
        "effect.execute": EffectExecuteExecutor(),
    }

    def executor_lookup(*, binding: BindingKind, node_id: str, region: str | None) -> NodeExecutor:
        del region
        if binding is not BindingKind.NODE_EXECUTOR:
            raise KeyError(f"unexpected binding {binding!r}")
        if node_id not in executors:
            raise KeyError(f"no executor for node_id={node_id!r}")
        return executors[node_id]

    def runtime_view_factory(agent_state: Any) -> Any:
        del agent_state
        return _build_runtime_view(gateway)

    registry = StrategyRegistry()
    registry.register(
        NodeExecutorStrategy(
            executor_lookup=executor_lookup,
            node_runtime_view_factory=runtime_view_factory,
        )
    )
    return registry


def _make_outer_registry(
    *,
    gateway: _StubEffectGateway,
    observe_recorder: _ObserveRecorder,
) -> StrategyRegistry:
    """Outer registry with real executors for every act node."""
    executors: dict[str, NodeExecutor] = {
        "act.validate": ActValidateExecutor(),
        "act.authorize": ActAuthorizeExecutor(),
        "act.approve.gate": ApproveGateExecutor(),
        "intervene.resume": ResumeExecutor(),
        "act.envelope": ActEnvelopeExecutor(),
        "act.fanout": ActFanoutExecutor(),
        "act.join": ActJoinExecutor(),
        "act.observe": observe_recorder,
    }

    def executor_lookup(*, binding: BindingKind, node_id: str, region: str | None) -> NodeExecutor:
        del region
        if binding is not BindingKind.NODE_EXECUTOR:
            raise KeyError(f"unexpected binding {binding!r}")
        if node_id not in executors:
            raise KeyError(f"no executor for node_id={node_id!r}")
        return executors[node_id]

    def runtime_view_factory(agent_state: Any) -> Any:
        del agent_state
        return _build_runtime_view(gateway)

    registry = StrategyRegistry()
    registry.register(
        NodeExecutorStrategy(
            executor_lookup=executor_lookup,
            node_runtime_view_factory=runtime_view_factory,
        )
    )
    return registry


async def _inner_runner(
    sub_plan: Plan,
    outer_state: Any,
    depth: int,
    outer_ports: PortRegistry | None,
    outer_mirror: dict | None,
) -> dict[str, Any]:
    """Recursive runner; mirrors the kernel-native PlanInterpreter.run closure."""
    del depth
    registry = outer_mirror.get("inner_registry") if outer_mirror else None
    if registry is None:
        raise RuntimeError(
            "test_act_subgraph_yaml_e2e: outer_mirror must carry "
            "the inner StrategyRegistry under 'inner_registry'"
        )
    inner = PlanInterpreter(
        registry=registry,
        results_by_phase=outer_mirror.get("results_by_phase", {}) if outer_mirror else {},
    )
    result = await inner.run(sub_plan, port_registry=outer_ports, outer_state=outer_state)
    return dict(result.output)


def _decision() -> Decision:
    """Minimal USE_TOOL decision the act chain accepts end-to-end."""
    from lca.contracts.models.core.execution.decision import ToolCall

    return Decision(
        decision_id="dec_subgraph_e2e",
        action_type="use_tool",
        rationale="kernel-level e2e through the act subgraph bundle",
        confidence=1.0,
        tool_calls=[
            ToolCall(call_id="call_subgraph_e2e", tool_name="bash", arguments={"op": "echo"})
        ],
        delegations=[],
    )


def _outer_state() -> Any:
    """Minimal AgentState-shaped object the strategies don't actually read."""
    from lca.contracts.models.core.state.state import AgentState, Budget

    return AgentState(trace_id="trace_subgraph_e2e", task="", budget=Budget())


@pytest.mark.asyncio
async def test_act_subgraph_bundle_full_chain_visits_all_eight_nodes() -> None:
    """End-to-end: validate → authorize → envelope → fanout → dispatch →
    join → observe, driven by the *actual* ``bundles/act/act_subgraph.yaml``.

    Unlike :func:`tests/integration/test_act_dispatch_join_observe_e2e.py`
    which builds the spec inline, this test lifts the production
    bundle so a future regression in the bundle's edge predicates or
    reachability breaks the chain here. Asserts all 7 act nodes are
    visited in order, the inner ``effect.execute`` is called once,
    and ``act.observe`` receives the receipt.

    Per AGENTS.md §3 C10 the inner executor is still the unique effect
    entry — only the runtime ``effect_gateway`` capability is stubbed.
    """
    gateway = _StubEffectGateway(invocation_id="inv_subgraph_e2e")
    observe_recorder = _ObserveRecorder(inner=ActObserveExecutor())

    inner_registry = _make_inner_registry(gateway)
    outer_registry = _make_outer_registry(
        gateway=gateway,
        observe_recorder=observe_recorder,
    )
    outer_registry.register(
        SubgraphStrategy(
            recursive_runner=_inner_runner,
            max_depth=4,
        )
    )

    plan = _lift_bundle()
    # Pre-seed the outer port registry with the typed Decision the
    # entry (``act.validate``) reads; ``act.validate`` is the entry of
    # the lifted bundle, and the kernel's port-registry forwards
    # ``set_outer_input`` to it.
    port_registry = PortRegistry()
    port_registry.set_outer_input({"decision": _decision()})

    interpreter = PlanInterpreter(
        registry=outer_registry,
        results_by_phase={"inner_registry": inner_registry},
    )
    result = await interpreter.run(
        plan,
        port_registry=port_registry,
        outer_state=_outer_state(),
    )

    visited_ids = [v.node_id for v in result.visits]
    # PR-1b / ADR-0237: gate sits between authorize and envelope.
    # The default Decision carries needs_approval=False, so the gate
    # emits approval_routing.next_hint='approve_skipped' which matches
    # the in [approve_skipped, approve_approved] predicate on the
    # gate → envelope edge. On approve_skipped the chain continues to
    # envelope (the full pipeline runs).
    expected = [
        "act.validate",
        "act.authorize",
        "act.approve.gate",
        "act.envelope",
        "act.fanout",
        "act.dispatch",
        "act.join",
        "act.observe",
    ]
    assert visited_ids == expected, (
        f"act subgraph bundle did not drive the full 8-node sequence. "
        f"expected={expected} got={visited_ids}. If the chain stops at "
        f"'act.fanout' (next node 'act.dispatch' missing), bundle "
        f"edges are broken (Defect 1a). If it stops at 'act.join' "
        f"(next node 'act.observe' missing predicate), bundle edge "
        f"is broken (Defect 1b). If it stops at 'act.approve.gate' "
        f"the gate → envelope predicate is rejecting (PR-1b)."
    )

    # Inner effect gateway was actually invoked by the inner
    # ``effect.execute`` running inside the act.dispatch subgraph
    # delegate.
    assert gateway.calls, "effect_gateway was not invoked by effect.execute"
    assert len(gateway.calls) == 1

    # act.observe received the receipt.
    assert observe_recorder.captured, (
        "act.observe did not capture a receipt — kernel terminated after "
        "join or join's output was empty (regression of receipt/receipts "
        "port mismatch fixed in PR-3.8.5 fix1)"
    )
    observed = observe_recorder.captured[-1]
    assert isinstance(observed, EffectReceipt)
    assert observed.invocation_id == "inv_subgraph_e2e"
    assert observed.outcome is EffectOutcome.SUCCEEDED


__all__ = [
    "test_act_fanout_is_reachable_from_act_validate_in_bundle",
    "test_act_fanout_to_act_dispatch_carries_fanout_1to1_predicate",
    "test_act_join_to_act_observe_carries_join_1to1_predicate_not_true",
    "test_act_subgraph_bundle_full_chain_visits_all_eight_nodes",
    "test_bundle_yaml_has_no_duplicate_when_keys",
    "test_lifted_bundle_has_exactly_nine_edges",
    "test_no_direct_act_envelope_to_act_dispatch_edge",
]
