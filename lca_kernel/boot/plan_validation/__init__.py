"""Boot-time plan validation — fail-loud gate for malformed plans.

The kernel walks every plan referenced by a resolved profile and lifts
each one through :func:`lift_graph_spec`. Any :class:`PlanLiftError`
raises immediately so a malformed plan is caught at kernel startup,
not 5 minutes into the first run when the user notices the run failed.

Errors are **aggregated** across all plans before raising, so the
operator sees every problem in a single boot failure rather than
fixing them one at a time.

The hook is wired into :func:`lca_kernel.boot.boot.run_resolved_kernel`
between K2 (``compile_run_plan``) and K3 (``_boot_context``). It runs
on every boot including tests and minimal paths — the only escape is
when the profile carries no bundles (empty profile is a no-op).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan
from lca.framework.graph.lifter import (
    _bundle_yaml_path,
    _lift_graph_spec_inner,
    lift_graph_spec,
    validate_predicates,
)
from lca.harness.profile.resolve.resolve import ResolvedProfile

from lca_kernel.boot.plan_validation.checks.compiled_run_plan import (
    check_compiled_run_plan,
)
from lca_kernel.boot.plan_validation.checks.cycle_port_dependency import (
    CyclePortDependencyCheck,
)
from lca_kernel.boot.plan_validation.checks.cycle_terminal import (
    CycleHasTerminalCheck,
)
from lca_kernel.boot.plan_validation.checks.entry_uniqueness import (
    EntryUniquenessCheck,
)
from lca_kernel.boot.plan_validation.checks.max_visits_bounds import (
    MaxVisitsBoundsCheck,
)
from lca_kernel.boot.plan_validation.checks.max_visits_vs_scc import (
    MaxVisitsVsSccCheck,
)
from lca_kernel.boot.plan_validation.checks.predicate_wellformed import (
    PredicateWellformedCheck,
)
from lca_kernel.boot.plan_validation.checks.subgraph_port_contract import (
    SubgraphPortContractCheck,
)

from .checks.profile_topology import check_profile_topology


def validate_profile_plans(resolved: ResolvedProfile) -> None:
    """Lift every plan reachable from ``resolved`` and aggregate failures.

    The validator mirrors :func:`lca_kernel.plan.plan_compile._wrap_v2_plan`'s
    outer-plan selection (first non-``.subgraph`` bundle, with
    first-node-as-entry fallback) and recursively validates every
    subgraph plan reachable via :class:`SubgraphReference`. Aggregated
    :class:`PlanLiftError` instances are joined into a single failure
    with ``plan_id`` set to the profile name so the kernel refuses to
    start.

    Validation runs in two layers:

    - :func:`_check_plan_spec` — runs on the raw bundle mapping (yaml
      shape, string-DSL predicates, ``sub_spec_ref.entry_node``
      existence).
    - :func:`_check_lifted_plan` — runs on the lifted :class:`Plan`
      (typed-port wiring: every edge target's required input must be
      produced by some reachable predecessor; reachability: every
      non-entry node must be reachable from the plan entry).

    Both layers are aggregated into a single failure so the operator
    sees every problem in one boot pass instead of N.

    On success, a one-line ``✅`` message is written to stderr so the
    count surfaces in ``/tmp/lca-kernel.log``.
    """
    bundles: Sequence[str] = getattr(resolved, "bundles", ()) or ()
    if not bundles:
        return  # empty profile — nothing to validate

    profile_name = Path(resolved.profile_path).name or "<profile>"
    profile_dir = Path(resolved.profile_path).parent
    failures: list[PlanLiftError] = []
    validated = 0

    # Profile-level topology runs first: a malformed profile
    # (duplicate bundle paths, reserved/underscore-prefixed ids)
    # must surface as a structural failure before any plan
    # lifter walks the bundle list. Plan-level checks below
    # assume the profile itself is well-formed.
    bundles_tuple: tuple[str, ...] = tuple(bundles)
    failures.extend(
        check_profile_topology(bundles_tuple, profile_name=profile_name)
    )

    outer_mapping, outer_path = _select_outer_plan(bundles, profile_dir=profile_dir)
    if outer_mapping is None:
        return  # no plan-shaped bundle in this profile

    plan_id = str(outer_mapping.get("id", outer_path.stem if outer_path else "<plan>"))
    # Outer plan: full ``lift_graph_spec`` so termination and predicate
    # invariants are enforced (the kernel refuses to start without a
    # terminal node on the outer; subgraph plans are validated later
    # via the inner-only lifter that skips termination because their
    # lifecycle is controlled by the outer's ``binding_edge``).
    outer_plan, outer_errs = _check_plan_spec(
        outer_mapping, plan_id=plan_id, is_outer=True
    )
    failures.extend(outer_errs)
    if outer_plan is not None:
        failures.extend(_check_lifted_plan(outer_plan, plan_id=plan_id))
        # Post-lift K2 compile invariants run on the outer plan
        # only: inner subgraph plans are entered through
        # ``SubgraphStrategy`` rather than compiled, so the
        # multi-node / entry-as-delegate / terminal-port checks
        # apply to the outer plan alone.
        failures.extend(
            check_compiled_run_plan(outer_plan, plan_id=plan_id)
        )
        validated += 1

    # Always recurse into inner sub_spec_ref plans so the user sees
    # all problems at once (per the "aggregate errors" contract).
    # ``path_resolver`` resolves inner ``plan_ref`` against the outer
    # bundle's directory first (matches the legacy ``base_dir``
    # semantics) then falls back to the lifter's repo-root resolver
    # — covers both production layouts (``bundles/foo.yaml``
    # repo-root-relative) and tests that put inner plans next to the
    # outer under a sandbox directory.
    def _resolve(plan_ref: str) -> Path:
        if outer_path is not None:
            candidate = outer_path.parent / plan_ref
            if candidate.exists():
                return candidate
        return _bundle_yaml_path(plan_ref)

    for inner_mapping, inner_id in _subgraph_ref_with_entry(
        outer_mapping,
        recurse=True,
        path_resolver=_resolve,
    ):
        inner_plan, inner_errs = _check_plan_spec(inner_mapping, plan_id=inner_id)
        failures.extend(inner_errs)
        if inner_plan is None:
            continue
        failures.extend(_check_lifted_plan(inner_plan, plan_id=inner_id))
        validated += 1

    if failures:
        raise _aggregate(failures, profile_name=profile_name)

    print(
        f"✅ profile {profile_name}: {validated} plans validated",
        file=sys.stderr,
    )


def _check_plan_spec(
    mapping: Mapping[str, Any],
    *,
    plan_id: str,
    is_outer: bool = False,
) -> tuple[Plan | None, list[PlanLiftError]]:
    """Spec-layer validation: shape, DSL, subgraph entry-node typo.

    Returns the lifted :class:`Plan` (or ``None`` if lifting failed)
    plus every error encountered. Errors are aggregated, not raised,
    so the caller can present all problems at once.

    When ``is_outer=True``, the full :func:`lift_graph_spec` is used
    (with ``_validate_termination`` + predicate validation). Inner
    subgraph plans use :func:`_lift_graph_spec_inner` so subgraph
    lifecycle is controlled by the outer's ``binding_edge`` rather
    than an inner terminal node.
    """
    errors: list[PlanLiftError] = []
    string_err = _check_string_predicate(mapping, plan_id=plan_id)
    if string_err is not None:
        errors.append(string_err)
        # Don't return early — still lift so the predicate/port
        # contract checks can aggregate alongside the string-DSL
        # finding into a single failure.

    with_entry = _apply_entry_fallback(mapping)
    try:
        # Outer plans run the full ``lift_graph_spec`` (terminates +
        # predicate invariants). Inner subgraph plans skip
        # ``_validate_termination`` because subgraph lifecycle is
        # bound to the outer caller's ``binding_edge``, not an
        # inner terminal node — but predicate + port-shape checks
        # still apply via ``validate_predicates``.
        plan = _lift_with_optional_termination(
            with_entry, enforce_termination=is_outer
        )
    except (PlanLiftError, ValidationError, ValueError, TypeError, KeyError) as exc:
        return None, errors + [_annotate(_normalize(exc), plan_id=plan_id)]
    return plan, errors


def _lift_with_optional_termination(
    spec: Mapping[str, Any], *, enforce_termination: bool
) -> Plan:
    """Run lifter matching what the kernel does at runtime.

    Outer plans go through the full :func:`lift_graph_spec` (with
    ``_validate_termination`` and ``validate_predicates``). Inner
    subgraph plans use :func:`_lift_graph_spec_inner` so the inner
    plan doesn't need its own terminal node — :class:`SubgraphStrategy`
    returns control to the outer kernel via ``binding_edge``, which
    matches what the kernel does at runtime (see :mod:`strategies.subgraph_strategy`).
    Predicate and port-shape checks still apply to inner plans via
    :func:`validate_predicates`.
    """
    if enforce_termination:
        return lift_graph_spec(spec)
    plan = _lift_graph_spec_inner(spec)
    validate_predicates(plan)
    return plan


def _check_lifted_plan(plan: Plan, *, plan_id: str) -> list[PlanLiftError]:
    """Plan-layer validation: typed-port wiring + reachability.

    Runs the registered :data:`_PLAN_CHECKS` against *plan*. Each check
    returns a :class:`PlanLiftError` or ``None``; failures are
    aggregated. New contract checks belong in :data:`_PLAN_CHECKS`
    below — composition over copy-paste.
    """
    errors: list[PlanLiftError] = []
    for check in _PLAN_CHECKS:
        err = check(plan, plan_id=plan_id)
        if err is not None:
            errors.append(err)
    return errors


def _check_typed_port_wiring(plan: Plan, *, plan_id: str) -> PlanLiftError | None:
    """Reject edges whose target expects a port no predecessor produces.

    The lifter validates single-edge predicate ports (:mod:`lifter`'s
    :func:`validate_predicates`) but does not run a typed-port
    reachability check across the plan — :class:`NodeIOSchema.required_inputs`
    is satisfied lazily by :class:`PortRegistry` at runtime, so a
    typo'd required port only blows up when the executor actually
    walks that node. This check computes the predecessor output set
    per node and rejects every missing-port case at boot time.

    Entry-node inputs are out of scope: the entry's inputs are
    supplied by the **outer caller** (parent plan via
    :class:`SubgraphStrategy` forwarding, or the top-level kernel).
    Computing "available" for an entry node would require caller-side
    context that the boot-time validator doesn't have.

    Subgraph delegate nodes (``subgraph_ref`` wired) are also
    out of scope: their inputs are forwarded by the surrounding
    caller via :class:`SubgraphStrategy`, not by an in-plan
    predecessor. The kernel reads them from the registry when the
    subgraph is entered, so a missing predecessor in the
    enclosing plan does not indicate a real wiring fault.
    """
    skip_ids = {
        n.id
        for n in plan.nodes
        if n.entry or n.subgraph_ref is not None
    }
    output_produced: dict[str, frozenset[str]] = {
        n.id: n.io_schema.output_names() for n in plan.nodes
    }
    predecessors: dict[str, frozenset[str]] = {n.id: frozenset() for n in plan.nodes}
    for edge in plan.edges:
        predecessors[edge.target] = predecessors.get(edge.target, frozenset()) | {edge.source}
    # Every node starts with its own declared outputs (these are
    # what it *emits*); fixed-point propagation then augments
    # ``available`` with the union of every predecessor's available
    # set, so a node's ``available`` is the union of "what I emit"
    # and "what flows in from reachable predecessors". Entry nodes
    # also start with their own outputs so a downstream node that
    # targets the entry as its predecessor (common in subgraph
    # delegates, where the entry is the delegate's entry) still
    # gets the right "available" set.
    available: dict[str, frozenset[str]] = {
        n.id: output_produced[n.id] for n in plan.nodes
    }
    changed = True
    while changed:
        changed = False
        for node_id, preds in predecessors.items():
            if not preds:
                continue
            merged: set[str] = set(available[node_id])
            for p in preds:
                merged |= available.get(p, frozenset())
            new = frozenset(merged)
            if new != available[node_id]:
                available[node_id] = new
                changed = True
    for node in plan.nodes:
        if node.id in skip_ids:
            continue
        required = node.io_schema.required_inputs()
        if not required:
            continue
        missing = [p for p in required if p not in available[node.id]]
        if not missing:
            continue
        return PlanLiftError(
            f"plan {plan_id!r}: node {node.id!r} required inputs "
            f"{missing!r} are not produced by any reachable predecessor "
            f"(available={sorted(available[node.id])}; "
            f"predecessors={sorted(predecessors[node.id])})",
            plan_id=plan_id,
            node_id=node.id,
        )
    return None


def _check_reachability(plan: Plan, *, plan_id: str) -> PlanLiftError | None:
    """Reject nodes that the entry cannot reach via the edge graph.

    A plan with disconnected subgraphs would silently skip those
    subgraphs at runtime — they exist in :class:`Plan.nodes` but
    no edge sequence ever visits them. Lift-time reachability
    catches this so a typo'd edge target or an accidentally
    orphaned node fails boot instead of being dead code.
    """
    if not plan.nodes:
        return None
    entry_id = next((n.id for n in plan.nodes if n.entry), None)
    if entry_id is None:
        return None
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
    unreachable = sorted(set(adj.keys()) - visited)
    if unreachable:
        return PlanLiftError(
            f"plan {plan_id!r}: nodes {unreachable!r} are unreachable from "
            f"entry node {entry_id!r}; they will never execute",
            plan_id=plan_id,
        )
    return None


def _check_self_loop_safe(plan: Plan, *, plan_id: str) -> PlanLiftError | None:
    """Reject self-loops with ``max_visits > 1``.

    A self-loop ``a → a`` with ``max_visits=1`` is fine — the kernel
    visits the node once and the loop terminates because the visit
    budget is exhausted. With ``max_visits > 1`` the same node can
    keep traversing the self-loop until the budget runs out, which
    silently inflates run cost without producing new state. Some
    executors genuinely need self-loops for retry semantics, so
    the cap is "raise only when the budget exceeds the safe
    single-visit value" — the operator can lower ``max_visits`` to
    silence the check.
    """
    for node in plan.nodes:
        if node.max_visits <= 1:
            continue
        for edge in plan.edges:
            if edge.source == node.id and edge.target == node.id:
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} has a self-loop "
                    f"with max_visits={node.max_visits}; this lets the "
                    f"interpreter revisit the node indefinitely and "
                    f"inflates run cost. Lower ``max_visits`` to 1 or "
                    f"remove the self-loop edge.",
                    plan_id=plan_id,
                    node_id=node.id,
                )
    return None


def _check_terminal_reachable_from_entry(
    plan: Plan, *, plan_id: str
) -> PlanLiftError | None:
    """Reject plans where no terminal node is reachable from the entry.

    The kernel terminates when it visits a node with
    ``terminal=True`` (or when a node's ``terminal_predicate``
    fires). If the BFS from the plan entry never reaches such a
    node the kernel runs forever (the classic "infinite loop"
    graph bug — see e.g. Cordis / react-flow / igraph stack
    traces). Catch the unreachable-termination case at boot time.
    """
    entry_id = next((n.id for n in plan.nodes if n.entry), None)
    if entry_id is None:
        return None
    terminals = {
        n.id for n in plan.nodes if n.terminal or n.io_schema.terminal_predicate is not None
    }
    if not terminals:
        # ``_check_lifted_plan``'s reachability + lifter's
        # ``_validate_termination`` already cover the no-terminal
        # case; skip here to avoid double-reporting.
        return None
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
    if not (terminals & visited):
        terminal_list = sorted(terminals)
        return PlanLiftError(
            f"plan {plan_id!r}: terminal nodes {terminal_list!r} are "
            f"unreachable from entry {entry_id!r}; the kernel will "
            f"run forever instead of terminating. Add an edge from "
            f"some reachable node to a terminal, or mark a reachable "
            f"node ``terminal: true``.",
            plan_id=plan_id,
        )
    return None


def _check_terminal_no_outgoing_edges(
    plan: Plan, *, plan_id: str
) -> PlanLiftError | None:
    """Reject ``terminal=True`` nodes with outgoing edges.

    A terminal node is meant to be a sink — once the kernel visits
    it the plan completes. Outgoing edges from a terminal node are
    dead code (the kernel never traverses them) and confuse the
    static graph view (operators see a "transition" that never
    fires). Subgraph delegate nodes are exempt because their
    binding_edge re-enters the outer caller, not a downstream
    node in the same plan.
    """
    for node in plan.nodes:
        if not node.terminal:
            continue
        if node.subgraph_ref is not None:
            continue
        outgoing = [e for e in plan.edges if e.source == node.id]
        if outgoing:
            return PlanLiftError(
                f"plan {plan_id!r}: terminal node {node.id!r} has "
                f"{len(outgoing)} outgoing edge(s); terminal nodes "
                f"are sinks and their edges never fire. Mark the "
                f"target node as the terminal or remove the edges.",
                plan_id=plan_id,
                node_id=node.id,
            )
    return None


def _check_cycle_has_terminal(
    plan: Plan, *, plan_id: str
) -> PlanLiftError | None:
    """Reject cycles that contain no terminal node.

    A strongly connected component without a terminal node is a
    classic "infinite loop" trap — the interpreter enters the
    cycle, traverses it until ``max_visits`` exhausts each node,
    and then dead-ends with no termination signal. Static
    reachability of a terminal elsewhere in the plan is not
    enough: a cycle that doesn't include a terminal leaves the
    kernel trapped inside it on every entry. The check
    complements :func:`_check_terminal_reachable_from_entry` —
    reachability asks "is a terminal reachable from entry", this
    check asks "does every cycle pass through a terminal".
    """
    # Tarjan-style SCC over the plan graph.
    node_ids = [n.id for n in plan.nodes]
    if not node_ids:
        return None
    index_of = {nid: i for i, nid in enumerate(node_ids)}
    adj: list[list[int]] = [[] for _ in node_ids]
    for edge in plan.edges:
        if edge.source in index_of and edge.target in index_of:
            adj[index_of[edge.source]].append(index_of[edge.target])
    terminals = {
        index_of[n.id]
        for n in plan.nodes
        if n.terminal or n.io_schema.terminal_predicate is not None
    }
    # Iterative Tarjan to avoid recursion limits on large graphs.
    index_counter = [0]
    stack: list[int] = []
    on_stack: set[int] = set()
    indices: dict[int, int] = {}
    lowlinks: dict[int, int] = {}
    sccs: list[list[int]] = []

    def strongconnect(start: int) -> None:
        work = [(start, 0)]
        call_stack: list[tuple[int, list[int]]] = []
        indices[start] = index_counter[0]
        lowlinks[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            v, pi = work[-1]
            if pi < len(adj[v]):
                w = adj[v][pi]
                work[-1] = (v, pi + 1)
                if w not in indices:
                    indices[w] = index_counter[0]
                    lowlinks[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, 0))
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])
            else:
                if lowlinks[v] == indices[v]:
                    scc: list[int] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.append(w)
                        if w == v:
                            break
                    sccs.append(scc)
                work.pop()

    for v in range(len(node_ids)):
        if v not in indices:
            strongconnect(v)
    for scc in sccs:
        if len(scc) <= 1:
            # Single-node SCC: self-loop already covered by
            # ``_check_self_loop_safe`` and a non-self-loop
            # single-node SCC trivially terminates via max_visits.
            continue
        if not (set(scc) & terminals):
            scc_names = sorted(node_ids[i] for i in scc)
            return PlanLiftError(
                f"plan {plan_id!r}: strongly connected component "
                f"{scc_names!r} contains no terminal node; the "
                f"interpreter will loop inside the cycle until every "
                f"node's ``max_visits`` budget exhausts and then "
                f"dead-end. Add a terminal node to the cycle or "
                f"break the cycle with a one-way exit edge.",
                plan_id=plan_id,
            )
    return None


_PLAN_CHECKS: tuple[Callable[[Plan, str], PlanLiftError | None], ...] = (
    # Original free-function checks (kept for backward compat with
    # the test that imports them by name).
    _check_typed_port_wiring,
    _check_reachability,
    _check_self_loop_safe,
    _check_terminal_reachable_from_entry,
    _check_terminal_no_outgoing_edges,
    # Class-based :class:`PlanCheck` strategies wired in via the
    # ``checks/`` subpackage. Each is a Strategy-style independent
    # unit that can be added/removed/parametrized without touching
    # the others — see ``checks/base.py`` for the contract.
    #
    # Mandatory structural checks (graph integrity, runtime safety):
    CyclePortDependencyCheck(),
    EntryUniquenessCheck(),
    MaxVisitsBoundsCheck(),
    PredicateWellformedCheck(),
    SubgraphPortContractCheck(),
    # Style / SSOT checks (skip in test fixtures that don't declare
    # these fields, but kept available for ``DEFAULT_CHECKS`` to
    # enable on production bundles via config):
    # - NodeIdNamingCheck
    # - PortNamingConventionCheck
    # - PlanIdAliasSuffixCheck
    # - BindingResolutionCheck
    # - NodeEventEmissionCheck
    # - UnusedPortsCheck (production inner subgraphs forward
    #   outputs to outer caller via SubgraphStrategy, so the
    #   plan-internal unused-output model produces false positives.
    #   Re-enable per-profile via extra config when ready.)
    # - CycleHasTerminalCheck (production phase cycles like
    #   think.main ↔ act.main rely on max_visits convergence, so
    #   the SCC-without-terminal check is opt-in via extra config.
    #   Keeping it disabled matches current production behavior;
    #   re-enable once phase cycles are broken up at the boundary
    #   by per-phase terminal predicates.)
    MaxVisitsVsSccCheck(),
)


def _normalize(exc: BaseException) -> PlanLiftError:
    """Coerce a non-:class:`PlanLiftError` exception into one."""
    if isinstance(exc, PlanLiftError):
        return exc
    return PlanLiftError(str(exc))


def _select_outer_plan(
    bundles: Sequence[str],
    *,
    profile_dir: Path,
) -> tuple[Mapping[str, Any] | None, Path | None]:
    """Return the first non-``.subgraph`` bundle mapping and resolved path.

    Mirrors :func:`lca_kernel.plan.plan_compile._wrap_v2_plan`: phase
    subgraph bundles (id ends with ``.subgraph``) are entered through
    :class:`SubgraphReference` rather than executed as the outer plan,
    so the validator skips them at the top level. Subgraph plans are
    still validated when reached via ``sub_spec_ref`` from the outer.
    """
    for entry in bundles:
        mapping = _load_bundle_mapping(entry, profile_dir=profile_dir)
        if mapping is None:
            continue
        if not _is_plan_spec(mapping):
            continue
        bundle_id = str(mapping.get("id", ""))
        if bundle_id.endswith(".subgraph"):
            continue
        path = _resolve_bundle_path(entry, profile_dir=profile_dir)
        return mapping, path
    return None, None


def _load_bundle_mapping(
    bundle_path: str,
    *,
    profile_dir: Path,
) -> Mapping[str, Any] | None:
    """Load a bundle yaml as a mapping. Returns None on missing/invalid files."""
    path = _resolve_bundle_path(bundle_path, profile_dir=profile_dir)
    if path is None or not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _resolve_bundle_path(bundle_path: str, *, profile_dir: Path) -> Path | None:
    """Resolve a bundle path to a real filesystem path (CWD first, then profile_dir)."""
    path = Path(bundle_path)
    if path.is_absolute():
        return path
    candidate = Path.cwd() / bundle_path
    if candidate.exists():
        return candidate
    candidate = profile_dir / bundle_path
    if candidate.exists():
        return candidate
    return path  # return as-is so callers can detect "not found"


def _is_plan_spec(mapping: Mapping[str, Any]) -> bool:
    """A v2 plan spec declares ``nodes``/``edges`` at the bundle root."""
    return "nodes" in mapping or "edges" in mapping


def _apply_entry_fallback(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of *mapping* with ``entry`` set if no node marks one.

    Mirrors :func:`lca_kernel.plan.plan_compile._wrap_v2_plan`'s
    first-node-as-entry fallback so the v2 Plan constructor's
    "exactly one entry" rule passes for legacy bundles that omit it.
    """
    spec = dict(mapping)
    nodes = list(spec.get("nodes") or ())
    if nodes and not any(
        isinstance(n, dict) and n.get("entry") for n in nodes
    ):
        nodes[0] = {**nodes[0], "entry": True}
        spec["nodes"] = nodes
    return spec


def _bundle_base_dir(bundle_path: Path | None, *, profile_dir: Path) -> Path:
    """Return the directory a bundle path resolves to, for resolving
    relative ``sub_spec_ref.plan_ref`` entries against it.
    """
    if bundle_path is None:
        return profile_dir
    return bundle_path.parent


def _subgraph_ref_with_entry(
    mapping: Mapping[str, Any],
    *,
    base_dir: Path | None = None,
    path_resolver: Callable[[str], Path] | None = None,
    recurse: bool = False,
    visited: set[str] | None = None,
) -> list[tuple[Mapping[str, Any], str]]:
    """Yield inner plan mappings + ids for every ``sub_spec_ref`` the spec reaches.

    Each inner mapping has ``entry`` injected from the corresponding
    ``sub_spec_ref.entry_node`` (mirroring the lifter's
    :func:`_subgraph_entry_schema` behavior) so the inner plan's
    "exactly one entry node required" invariant passes — subgraph
    bundles legitimately omit ``entry`` because the outer plan tells
    the kernel where to start.

    Inner ``plan_ref`` paths resolve via :func:`lca.framework.graph.lifter._bundle_yaml_path`
    by default — joining them with the outer bundle's directory
    previously produced ``bundles/bundles/<inner>.yaml`` for
    production layouts and silently skipped every reachable subgraph
    (the prior bug). ``path_resolver`` is overridable so tests can
    pin resolution to ``tmp_path`` without polluting the production
    ``bundles/`` tree.

    With ``recurse=True`` the walker also descends into inner plans'
    own ``sub_spec_ref`` nodes, so a chained subgraph
    (``phase_main_outer.yaml`` → ``think.yaml`` → ``think_reason.yaml``
    → ``concept/tool_fork.yaml``) is validated in a single boot pass
    instead of failing at runtime when the inner-inner subgraph is
    first lifted. ``visited`` deduplicates by resolved plan id so
    shared subgraphs (referenced by more than one path) aren't
    re-lifted.
    """
    del base_dir  # kept for backward-compat with the prior signature
    resolver = path_resolver or _bundle_yaml_path
    inner: list[tuple[Mapping[str, Any], str]] = []
    seen: set[str] = set() if visited is None else visited
    for raw in mapping.get("nodes", ()) or ():
        if not isinstance(raw, Mapping):
            continue
        sub_ref = raw.get("sub_spec_ref")
        if sub_ref is None:
            config = raw.get("config")
            if isinstance(config, Mapping):
                sub_ref = config.get("sub_spec_ref")
        if not isinstance(sub_ref, Mapping):
            continue
        plan_ref = str(sub_ref.get("plan_ref", "")).strip()
        entry_node = str(sub_ref.get("entry_node", "")).strip()
        if not plan_ref:
            continue
        try:
            inner_path = resolver(plan_ref)
        except (OSError, ValueError):
            continue
        if not inner_path.exists():
            continue
        try:
            raw_inner = yaml.safe_load(inner_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(raw_inner, dict):
            continue
        spec = dict(raw_inner)
        if "entry" not in spec and entry_node:
            spec["entry"] = entry_node
        inner_id = str(spec.get("id", plan_ref))
        if inner_id in seen:
            continue
        seen.add(inner_id)
        inner.append((spec, inner_id))
        if recurse:
            inner.extend(
                _subgraph_ref_with_entry(
                    spec,
                    path_resolver=resolver,
                    recurse=True,
                    visited=seen,
                )
            )
    return inner


# Strings that the lifter's :func:`_coerce_when` maps to ``None`` —
# the predicates evaluate to "always true" at runtime, but any other
# string is rejected at lift time (D4 typed-port cutover). The legacy
# string-DSL edge conditions silently fired every edge regardless of
# the upstream decision; we fail loud at boot so a misroute never
# reaches runtime.
_STRING_WHEN_ALIASES = frozenset({"true", "false", ""})


def _check_string_predicate(
    spec: Mapping[str, Any],
    *,
    plan_id: str,
) -> PlanLiftError | None:
    """Build a :class:`PlanLiftError` for a string-predicate edge, or None."""
    for raw in spec.get("edges", ()) or ():
        if not isinstance(raw, Mapping):
            continue
        when = raw.get("when")
        if isinstance(when, str) and when.strip().lower() not in _STRING_WHEN_ALIASES:
            edge_id = f"{raw.get('from', '?')}->{raw.get('to', '?')}"
            return PlanLiftError(
                f"plan {plan_id!r}: edge {edge_id!r}: string when: {when!r} is no longer supported; "
                "use a typed Predicate dict",
                plan_id=plan_id,
                edge_id=edge_id,
            )
    return None


def _aggregate(
    failures: list[PlanLiftError],
    *,
    profile_name: str,
) -> PlanLiftError:
    """Combine every per-plan failure into one :class:`PlanLiftError`."""
    lines: list[str] = []
    for err in failures:
        lines.append(f"- {err}")
    joined = "\n".join(lines)
    return PlanLiftError(
        f"profile {profile_name}: {len(failures)} plan(s) lifted with errors:\n{joined}",
        plan_id=profile_name,
    )


def _annotate(err: PlanLiftError, *, plan_id: str) -> PlanLiftError:
    """Re-raise *err* with the plan id in both the message and the
    structured ``plan_id`` field.

    The lifter already sets ``plan_id`` on most errors; we always
    prepend the plan id to the message so the aggregated reason is
    self-describing when multiple plans fail at once.
    """
    return PlanLiftError(
        f"plan {plan_id!r}: {err}",
        plan_id=plan_id,
        node_id=err.node_id,
        edge_id=err.edge_id,
        port_name=err.port_name,
    )


def _safe_lift(spec: Mapping[str, Any]) -> PlanLiftError | None:
    """Run :func:`lift_graph_spec` and normalize any failure to
    :class:`PlanLiftError`.

    The lifter raises a mix of exceptions for different defect
    classes: :class:`PlanLiftError` (typed-port invariant violations),
    Pydantic :class:`ValidationError` (Plan model validators), plus
    bare :class:`ValueError` / :class:`TypeError` / :class:`KeyError`
    from ``_lift_graph_spec_inner`` for structural defects that
    surface before the Plan model is constructed (e.g. ``nodes must
    be a sequence``, ``binding must be a BindingKind or string``,
    duplicate-port-name model validators). Every exception must be
    normalized into a :class:`PlanLiftError` so the boot hook fails
    loud instead of letting structural defects leak into the kernel.
    """
    try:
        lift_graph_spec(spec)
        return None
    except PlanLiftError as exc:
        return exc
    except ValidationError as exc:
        return PlanLiftError(str(exc))
    except (ValueError, TypeError, KeyError) as exc:
        return PlanLiftError(str(exc))


__all__ = ["validate_profile_plans"]
