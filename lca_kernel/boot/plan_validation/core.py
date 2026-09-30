"""Core orchestration for boot-time plan validation.

This module owns the ``validate_profile_plans`` entry point plus the
spec/lift helpers and error aggregation that tie the focused check
modules together:

- :mod:`lca_kernel.boot.plan_validation.bundle_mapping` — bundle
  loading, outer-plan selection, subgraph discovery.
- :mod:`lca_kernel.boot.plan_validation.predicates` — string-DSL
  predicate rejection.
- :mod:`lca_kernel.boot.plan_validation.typed_ports` and
  :mod:`lca_kernel.boot.plan_validation.reachability` — post-lift
  graph invariants (free-function forms kept for backward compat).

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

from pydantic import ValidationError

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan
from lca.framework.graph.lift.graph_spec import (
    _lift_graph_spec_inner,
)
from lca.framework.graph.lift.subgraph_contract import (
    _bundle_yaml_path,
)
from lca.framework.graph.lifter import (
    lift_graph_spec,
    validate_predicates,
)
from lca.harness.profile.resolve.resolve import ResolvedProfile
from lca_kernel.boot.plan_validation.bundle_mapping import (
    _apply_entry_fallback,
    _select_outer_plan,
    _subgraph_ref_with_entry,
)
from lca_kernel.boot.plan_validation.checks.admit_recovery_edge import (
    AdmitRecoveryEdgeCheck,
)
from lca_kernel.boot.plan_validation.checks.compiled_run_plan import (
    check_compiled_run_plan,
)
from lca_kernel.boot.plan_validation.checks.cycle_port_dependency import (
    CyclePortDependencyCheck,
)
from lca_kernel.boot.plan_validation.checks.entry_uniqueness import (
    EntryUniquenessCheck,
)
from lca_kernel.boot.plan_validation.checks.node_executor_coverage import (
    check_node_executor_coverage,
)
from lca_kernel.boot.plan_validation.checks.predicate_wellformed import (
    PredicateWellformedCheck,
)
from lca_kernel.boot.plan_validation.checks.profile_topology import (
    check_profile_topology,
)
from lca_kernel.boot.plan_validation.checks.subgraph_port_contract import (
    SubgraphPortContractCheck,
)
from lca_kernel.boot.plan_validation.checks.use_tool_reask_edge import (
    UseToolReaskEdgeCheck,
)
from lca_kernel.boot.plan_validation.predicates import (
    _check_string_predicate,
)
from lca_kernel.boot.plan_validation.reachability import (
    _check_reachability,
    _check_terminal_no_outgoing_edges,
    _check_terminal_reachable_from_entry,
)
from lca_kernel.boot.plan_validation.typed_ports import (
    _check_typed_port_wiring,
)

_PLAN_CHECKS: tuple[Callable[[Plan, str], PlanLiftError | None], ...] = (
    # Original free-function checks (kept for backward compat with
    # the test that imports them by name).
    _check_typed_port_wiring,
    _check_reachability,
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
    PredicateWellformedCheck(),
    SubgraphPortContractCheck(),
    # M1 outer edge SSOT: bounded admit_recovery on phase.main.outer.
    AdmitRecoveryEdgeCheck(),
    UseToolReaskEdgeCheck(),
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
    #   think.main ↔ act.main rely on terminal_predicate convergence,
    #   so the SCC-without-terminal check is opt-in via extra config.
    #   Keeping it disabled matches current production behavior;
    #   re-enable once phase cycles are broken up at the boundary
    #   by per-phase terminal predicates.)
)


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
    failures.extend(check_profile_topology(bundles_tuple, profile_name=profile_name))

    outer_mapping, outer_path = _select_outer_plan(bundles, profile_dir=profile_dir)

    # Node-executor coverage runs pre-lift on the raw bundle mappings
    # because the lifter discards the ``factory`` field after mapping
    # it to ``BindingKind.NODE_EXECUTOR`` (see
    # :func:`lca.framework.graph.lifter._binding_from_factory_or_binding`).
    # Collect every plan mapping we will validate (outer + every inner
    # ``sub_spec_ref`` subgraph reachable from the outer) and assert
    # each ``factory`` resolves to a plugin spec in the resolved
    # profile. A missing entry is the bug that used to surface as
    # ``NodeExecutor lookup miss`` mid-run; now it fails boot with a
    # clear message naming the missing factory.
    if outer_mapping is not None:
        coverage_mappings: list[Mapping[str, Any]] = [outer_mapping]
        for inner_mapping, _inner_id in _subgraph_ref_with_entry(
            outer_mapping,
            recurse=True,
        ):
            coverage_mappings.append(inner_mapping)
        failures.extend(check_node_executor_coverage(coverage_mappings, resolved))

    if outer_mapping is None:
        return  # no plan-shaped bundle in this profile

    plan_id = str(outer_mapping.get("id", outer_path.stem if outer_path else "<plan>"))
    # Outer plan: full ``lift_graph_spec`` so termination and predicate
    # invariants are enforced (the kernel refuses to start without a
    # terminal node on the outer; subgraph plans are validated later
    # via the inner-only lifter that skips termination because their
    # lifecycle is controlled by the outer's ``binding_edge``).
    outer_plan, outer_errs = _check_plan_spec(outer_mapping, plan_id=plan_id, is_outer=True)
    failures.extend(outer_errs)
    if outer_plan is not None:
        failures.extend(_check_lifted_plan(outer_plan, plan_id=plan_id))
        # Post-lift K2 compile invariants run on the outer plan
        # only: inner subgraph plans are entered through
        # ``SubgraphStrategy`` rather than compiled, so the
        # multi-node / entry-as-delegate / terminal-port checks
        # apply to the outer plan alone.
        failures.extend(check_compiled_run_plan(outer_plan, plan_id=plan_id))
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
        plan = _lift_with_optional_termination(with_entry, enforce_termination=is_outer)
    except (PlanLiftError, ValidationError, ValueError, TypeError, KeyError) as exc:
        return None, [*errors, _annotate(_normalize(exc), plan_id=plan_id)]
    return plan, errors


def _lift_with_optional_termination(spec: Mapping[str, Any], *, enforce_termination: bool) -> Plan:
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


def _normalize(exc: BaseException) -> PlanLiftError:
    """Coerce a non-:class:`PlanLiftError` exception into one."""
    if isinstance(exc, PlanLiftError):
        return exc
    return PlanLiftError(str(exc))


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
