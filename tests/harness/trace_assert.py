"""Topology and mode-invariant assertions over TraceBundle.

Failures always embed format_case_digest so pytest output is locatable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from lca.contracts.result import Result
from lca.contracts.telemetry import SpanName
from tests.harness.collector import TraceBundle
from tests.harness.report import format_case_digest

InvariantFn = Callable[[TraceBundle, Result], None]


def _fail(
    msg: str, bundle: TraceBundle, result: Result | None = None, title: str = "ASSERT"
) -> None:
    raise AssertionError(f"{msg}\n{format_case_digest(bundle, title=title, result=result)}")


def assert_must_include_spans(
    bundle: TraceBundle,
    names: Sequence[str],
    *,
    result: Result | None = None,
) -> None:
    present = set(bundle.names())
    missing = [n for n in names if n not in present]
    if missing:
        _fail(
            f"Missing spans {missing}. Present={sorted(present)}",
            bundle,
            result,
            title="missing spans",
        )


def assert_shared_trace_id(bundle: TraceBundle, result: Result | None = None) -> None:
    team_roots = bundle.by_name(SpanName.RUN_TEAM.value)
    if team_roots:
        tid = team_roots[0].trace_id
        bad = [s for s in bundle.walk(team_roots[0]) if s.trace_id != tid]
        if bad:
            _fail(
                f"Span tree under run.team has mixed trace_ids: {[b.name for b in bad]}",
                bundle,
                result,
                title="mixed trace_id",
            )
        return
    # solo / non-team: all spans same trace under run.agent
    agent_roots = bundle.by_name(SpanName.RUN_AGENT.value)
    if agent_roots:
        tid = agent_roots[0].trace_id
        bad = [s for s in bundle.walk(agent_roots[0]) if s.trace_id != tid]
        if bad:
            _fail(
                f"Span tree under run.agent has mixed trace_ids: {[b.name for b in bad]}",
                bundle,
                result,
                title="mixed trace_id",
            )


def assert_parent_chain_walkable(
    bundle: TraceBundle,
    root: str,
    leaf: str,
    *,
    result: Result | None = None,
) -> None:
    if not bundle.has_path_to(root, leaf):
        _fail(
            f"No path from {root!r} to leaf prefix {leaf!r}",
            bundle,
            result,
            title="parent chain",
        )


def assert_pipeline_sequential(bundle: TraceBundle, result: Result) -> None:
    delegations = bundle.by_name(SpanName.DELEGATION.value)
    if len(delegations) < 1:
        _fail("pipeline expects ≥1 delegation", bundle, result)


def assert_fan_out_all_members(bundle: TraceBundle, result: Result) -> None:
    delegations = bundle.by_name(SpanName.DELEGATION.value)
    if len(delegations) < 2:
        _fail(f"fan_out expects ≥2 delegations, got {len(delegations)}", bundle, result)
    if not bundle.by_name(SpanName.TEAM_SYNTHESIS.value):
        _fail("fan_out expects team.synthesis span", bundle, result)


def assert_board_consults_members(bundle: TraceBundle, result: Result) -> None:
    agent_roles = {
        s.attributes.get("agent_role")
        for s in bundle.by_name(SpanName.RUN_AGENT.value)
        if s.attributes.get("agent_role")
    }
    transport = bundle.by_name(SpanName.TRANSPORT_REQUEST.value)
    if len(agent_roles) < 2:
        _fail(f"lead path expects multi-agent roles; roles={agent_roles}", bundle, result)
    if not transport:
        _fail("lead path expects transport.request", bundle, result)


def assert_lead_transport_chain(bundle: TraceBundle, result: Result) -> None:
    # ADR-0037 拓扑：run.team → run.agent(lead) → delegation → run.agent(member)。
    # transport.request 仍在（机制平面），但不再是成员的结构性父链承载者。
    assert_must_include_spans(
        bundle,
        [
            SpanName.RUN_TEAM.value,
            SpanName.DELEGATION.value,
            SpanName.TRANSPORT_REQUEST.value,
            SpanName.RUN_AGENT.value,
        ],
        result=result,
    )
    assert_parent_chain_walkable(
        bundle, SpanName.RUN_TEAM.value, SpanName.DELEGATION.value, result=result
    )
    # 成员 run.agent 挂在 delegation 之下（一等委派），不再是 0 秒 transport 化石
    assert_parent_chain_walkable(
        bundle, SpanName.DELEGATION.value, SpanName.RUN_AGENT.value, result=result
    )
    assert_shared_trace_id(bundle, result)
    if not bundle.has_path_to(SpanName.RUN_TEAM.value, SpanName.LLM_CHAT.value):
        _fail("lead path: cannot walk run.team→llm.chat", bundle, result)


def assert_team_root(bundle: TraceBundle, result: Result) -> None:
    assert_must_include_spans(bundle, [SpanName.RUN_TEAM.value], result=result)


def assert_swarm_rounds(bundle: TraceBundle, result: Result) -> None:
    if not bundle.by_name(SpanName.TEAM_ROUND.value):
        _fail("swarm/debate expects team.round spans", bundle, result)


INVARIANTS: dict[str, InvariantFn] = {
    "pipeline_sequential": assert_pipeline_sequential,
    "fan_out_all_members": assert_fan_out_all_members,
    "board_consults_members": assert_board_consults_members,
    "lead_transport_chain": assert_lead_transport_chain,
    "team_root": assert_team_root,
    "swarm_rounds": assert_swarm_rounds,
    "shared_trace": lambda b, r: assert_shared_trace_id(b, r),
}


def assert_trace_expect(
    bundle: TraceBundle,
    result: Result,
    expect: dict[str, Any] | None,
    *,
    case: str = "case",
) -> None:
    """Apply expect.trace / expect.invariants; failures include full digest."""
    if not expect:
        return
    try:
        trace = expect.get("trace") or {}
        must = trace.get("must_include_spans") or []
        if must:
            assert_must_include_spans(bundle, must, result=result)
        if trace.get("require_shared_trace_id", True):
            assert_shared_trace_id(bundle, result)
        root = trace.get("parent_root")
        leaf = trace.get("parent_leaf")
        if root and leaf:
            assert_parent_chain_walkable(bundle, root, leaf, result=result)

        for inv_name in expect.get("invariants") or []:
            fn = INVARIANTS.get(inv_name)
            if fn is None:
                raise KeyError(f"Unknown invariant {inv_name!r}. Known: {list(INVARIANTS)}")
            fn(bundle, result)

        result_exp = expect.get("result") or {}
        if "status" in result_exp and result.status != result_exp["status"]:
            _fail(
                f"status {result.status!r} != {result_exp['status']!r}",
                bundle,
                result,
                title=case,
            )
        if "min_steps" in result_exp and result.total_steps < int(result_exp["min_steps"]):
            _fail(
                f"total_steps {result.total_steps} < {result_exp['min_steps']}",
                bundle,
                result,
                title=case,
            )
    except AssertionError:
        raise
    except Exception as exc:
        _fail(f"unexpected while asserting: {exc!r}", bundle, result, title=case)
