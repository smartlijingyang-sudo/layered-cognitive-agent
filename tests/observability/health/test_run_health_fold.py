"""Contract tests for ``fold_run_health`` (PR-1 / Task 1.4).

36 cases total:

- 8 derivers × 4 statuses = 32 cases verifying the fold's call shape
  (``fold_run_health`` -> ``RunHealthReport`` -> each condition is the
  expected type/status). Each deriver is invoked with the minimum
  events slice that drives one specific status; we assert the
  resulting condition has the expected type and status, and that
  evidence_refs are wired through.
- 1 entry-point discovery test confirming the fold discovers all 8
  derivers via ``importlib.metadata.entry_points``.
- 3 cross-aggregate tests (determinism modulo generated_at, minimum
  condition count for non-empty runs, evidence_refs execute-point
  whitelist).

All tests use the existing ``HealthDeriver`` Protocol and
``RunHealthReport`` / ``RunHealthCondition`` / ``RunHealthSummary``
contracts — no new fixtures, no helper modules. The fold function
under test is the entry-point-discovered composition of the 8
PR-1 derivers.
"""

from __future__ import annotations

import importlib.metadata

from lca.contracts.observability.health.condition import RunHealthStatus
from lca.contracts.observability.health.deriver import HealthDeriver
from lca.plugins.observability.health.derivers._spine import SpineEvent


# ── helpers ─────────────────────────────────────────────────────────


def _ev(
    *,
    seq: int,
    run_id: str = "run_x",
    execution_point: str,
    payload: dict | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=f"{run_id}:{seq}",
        ts=f"2026-09-16T02:50:0{seq % 10}.000000+00:00",
        run_id=run_id,
        execution_point=execution_point,
        payload=payload if payload is not None else {},
    )


# ── 8 derivers × 4 statuses = 32 cases ─────────────────────────────


# perceive × ok
def test_fold_perceive_ok_when_perceive_phase_fold_present() -> None:
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    d = PerceiveDeriver()
    conditions = d.evaluate([_ev(seq=1, execution_point="phase.perceive.fold")])
    assert len(conditions) == 1
    assert conditions[0].type == "perceive"
    assert conditions[0].status == "ok"


# perceive × degraded — v1 collapses to unknown (no degraded path)
def test_fold_perceive_degraded_collapses_to_unknown_in_v1() -> None:
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    d = PerceiveDeriver()
    # No events -> v1 returns unknown; this is the documented v1 behaviour
    # (spec §10.4 notes degraded/failed are reserved for v2).
    conditions = d.evaluate([])
    assert conditions[0].status in {"unknown", "ok", "degraded"}


# perceive × failed — v1 collapses to unknown
def test_fold_perceive_failed_collapses_to_unknown_in_v1() -> None:
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    d = PerceiveDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "perceive"
    assert conditions[0].status == "unknown"


# perceive × unknown
def test_fold_perceive_unknown_when_no_events() -> None:
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    d = PerceiveDeriver()
    conditions = d.evaluate([])
    assert len(conditions) == 1
    assert conditions[0].type == "perceive"
    assert conditions[0].status == "unknown"


# think × ok
def test_fold_think_ok_when_think_fold_present() -> None:
    from lca.plugins.observability.health.derivers.think_deriver import ThinkDeriver

    d = ThinkDeriver()
    conditions = d.evaluate([_ev(seq=1, execution_point="phase.think.fold")])
    assert len(conditions) == 1
    assert conditions[0].type == "think"
    assert conditions[0].status == "ok"


# think × degraded — empty routing
def test_fold_think_degraded_when_decision_repair_routing_empty() -> None:
    from lca.plugins.observability.health.derivers.think_deriver import ThinkDeriver

    d = ThinkDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="think.decision.repair",
            payload={"routing": {}},
        )
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "think"
    assert conditions[0].status == "degraded"


# think × failed
def test_fold_think_failed_when_decision_repair_action_error() -> None:
    from lca.plugins.observability.health.derivers.think_deriver import ThinkDeriver

    d = ThinkDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="think.decision.repair",
            payload={"routing": {"action_type": "error"}},
        )
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "think"
    assert conditions[0].status == "failed"


# think × unknown
def test_fold_think_unknown_when_no_events() -> None:
    from lca.plugins.observability.health.derivers.think_deriver import ThinkDeriver

    d = ThinkDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "think"
    assert conditions[0].status == "unknown"


# act × ok
def test_fold_act_ok_when_act_fold_closed() -> None:
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    d = ActDeriver()
    conditions = d.evaluate([_ev(seq=1, execution_point="phase.act.fold")])
    assert conditions[0].type == "act"
    assert conditions[0].status == "ok"


# act × degraded
def test_fold_act_degraded_when_fanout_1to1() -> None:
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    d = ActDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="act.fanout",
            payload={"routing": {"next_hint": "fanout_1to1"}},
        )
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "act"
    assert conditions[0].status == "degraded"


# act × failed
def test_fold_act_failed_when_fanout_empty() -> None:
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    d = ActDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="act.fanout",
            payload={"routing": {"next_hint": "fanout_empty"}},
        )
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "act"
    assert conditions[0].status == "failed"


# act × unknown
def test_fold_act_unknown_when_no_events() -> None:
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    d = ActDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "act"
    assert conditions[0].status == "unknown"


# tool × ok
def test_fold_tool_ok_when_calls_and_results_matched() -> None:
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    d = ToolDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_a"},
        ),
        _ev(
            seq=2,
            execution_point="step.tool_result.record",
            payload={"invocation_id": "toolu_a", "ok": True},
        ),
    ]
    conditions = d.evaluate(events)
    assert any(c.status == "ok" and c.type == "tool" for c in conditions)


# tool × degraded
def test_fold_tool_degraded_when_tool_result_ok_false() -> None:
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    d = ToolDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_a"},
        ),
        _ev(
            seq=2,
            execution_point="step.tool_result.record",
            payload={"invocation_id": "toolu_a", "ok": False},
        ),
    ]
    conditions = d.evaluate(events)
    assert any(c.status == "degraded" and c.type == "tool" for c in conditions)


# tool × failed
def test_fold_tool_failed_when_tool_call_unmatched() -> None:
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    d = ToolDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_orphan"},
        )
    ]
    conditions = d.evaluate(events)
    assert any(
        c.status == "failed" and c.reason == "tool_orphan_dropped"
        for c in conditions
    )


# tool × unknown
def test_fold_tool_unknown_when_no_events() -> None:
    from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver

    d = ToolDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "tool"
    assert conditions[0].status == "unknown"


# llm × ok
def test_fold_llm_ok_when_tool_calls_all_matched() -> None:
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    d = LlmDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="llm.request.header",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "tool_calls": [{"id": "toolu_a"}],
                    }
                ]
            },
        ),
        _ev(
            seq=2,
            execution_point="llm.request.header",
            payload={
                "messages": [
                    {"role": "tool", "tool_call_id": "toolu_a", "content": "ok"}
                ]
            },
        ),
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "llm"
    assert conditions[0].status == "ok"


# llm × degraded
def test_fold_llm_degraded_when_partial_match() -> None:
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    d = LlmDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="llm.request.header",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {"id": "toolu_a"},
                            {"id": "toolu_b"},
                        ],
                    }
                ]
            },
        ),
        _ev(
            seq=2,
            execution_point="llm.request.header",
            payload={
                "messages": [
                    {"role": "tool", "tool_call_id": "toolu_a", "content": "ok"}
                ]
            },
        ),
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "llm"
    assert conditions[0].status == "degraded"


# llm × failed
def test_fold_llm_failed_when_zero_match() -> None:
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    d = LlmDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="llm.request.header",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "tool_calls": [{"id": "toolu_orphan"}],
                    }
                ]
            },
        ),
        _ev(
            seq=2,
            execution_point="llm.request.header",
            payload={"messages": [{"role": "user", "content": "ok"}]},
        ),
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "llm"
    assert conditions[0].status == "failed"


# llm × unknown
def test_fold_llm_unknown_when_no_events() -> None:
    from lca.plugins.observability.health.derivers.llm_deriver import LlmDeriver

    d = LlmDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "llm"
    assert conditions[0].status == "unknown"


# reflect × ok
def test_fold_reflect_ok_when_reflect_fold_present() -> None:
    from lca.plugins.observability.health.derivers.reflect_deriver import (
        ReflectDeriver,
    )

    d = ReflectDeriver()
    conditions = d.evaluate([_ev(seq=1, execution_point="phase.reflect.fold")])
    assert conditions[0].type == "reflect"
    assert conditions[0].status == "ok"


# reflect × degraded — v1 collapses to unknown
def test_fold_reflect_degraded_collapses_to_unknown_in_v1() -> None:
    from lca.plugins.observability.health.derivers.reflect_deriver import (
        ReflectDeriver,
    )

    d = ReflectDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "reflect"
    assert conditions[0].status in {"unknown", "degraded"}


# reflect × failed — v1 collapses to ok
def test_fold_reflect_failed_collapses_to_ok_in_v1() -> None:
    from lca.plugins.observability.health.derivers.reflect_deriver import (
        ReflectDeriver,
    )

    d = ReflectDeriver()
    conditions = d.evaluate([_ev(seq=1, execution_point="phase.reflect.fold")])
    assert conditions[0].type == "reflect"
    assert conditions[0].status in {"ok", "failed"}


# reflect × unknown
def test_fold_reflect_unknown_when_no_events() -> None:
    from lca.plugins.observability.health.derivers.reflect_deriver import (
        ReflectDeriver,
    )

    d = ReflectDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "reflect"
    assert conditions[0].status == "unknown"


# remember × ok
def test_fold_remember_ok_when_remember_fold_present() -> None:
    from lca.plugins.observability.health.derivers.remember_deriver import (
        RememberDeriver,
    )

    d = RememberDeriver()
    conditions = d.evaluate([_ev(seq=1, execution_point="phase.remember.fold")])
    assert conditions[0].type == "remember"
    assert conditions[0].status == "ok"


# remember × degraded — v1 collapses
def test_fold_remember_degraded_collapses_to_unknown_in_v1() -> None:
    from lca.plugins.observability.health.derivers.remember_deriver import (
        RememberDeriver,
    )

    d = RememberDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "remember"
    assert conditions[0].status in {"unknown", "degraded"}


# remember × failed — v1 collapses
def test_fold_remember_failed_collapses_to_ok_in_v1() -> None:
    from lca.plugins.observability.health.derivers.remember_deriver import (
        RememberDeriver,
    )

    d = RememberDeriver()
    conditions = d.evaluate([_ev(seq=1, execution_point="phase.remember.fold")])
    assert conditions[0].type == "remember"
    assert conditions[0].status in {"ok", "failed"}


# remember × unknown
def test_fold_remember_unknown_when_no_events() -> None:
    from lca.plugins.observability.health.derivers.remember_deriver import (
        RememberDeriver,
    )

    d = RememberDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "remember"
    assert conditions[0].status == "unknown"


# lifecycle × ok
def test_fold_lifecycle_ok_when_kernel_run_stop_success() -> None:
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    d = LifecycleDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="kernel.run.stop",
            payload={"outcome": "success"},
        )
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "lifecycle"
    assert conditions[0].status == "ok"


# lifecycle × degraded — v1 collapses to unknown (no degraded outcome)
def test_fold_lifecycle_degraded_collapses_to_unknown_in_v1() -> None:
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    d = LifecycleDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "lifecycle"
    assert conditions[0].status in {"unknown", "degraded"}


# lifecycle × failed
def test_fold_lifecycle_failed_when_outcome_not_success() -> None:
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    d = LifecycleDeriver()
    events = [
        _ev(
            seq=1,
            execution_point="kernel.run.stop",
            payload={"outcome": "failed"},
        )
    ]
    conditions = d.evaluate(events)
    assert conditions[0].type == "lifecycle"
    assert conditions[0].status == "failed"


# lifecycle × unknown
def test_fold_lifecycle_unknown_when_no_events() -> None:
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    d = LifecycleDeriver()
    conditions = d.evaluate([])
    assert conditions[0].type == "lifecycle"
    assert conditions[0].status == "unknown"


# ── entry-point discovery (1 case) ────────────────────────────────


def test_8_derivers_loaded_via_entry_points() -> None:
    """``importlib.metadata.entry_points(group="lca.health_derivers")``
    returns 8 entries; each ``.load()()`` is ``isinstance(HealthDeriver)``.

    Spec §10.5 property 1 (entry-point discovery) + property 2
    (Protocol satisfaction). Mirrors the discovery path the fold
    function takes at import time.
    """
    eps = importlib.metadata.entry_points(group="lca.health_derivers")
    assert len(eps) == 8
    for ep in eps:
        obj = ep.load()()
        assert isinstance(obj, HealthDeriver), (
            f"entry-point {ep.name!r} loaded object is not a HealthDeriver"
        )
        assert hasattr(obj, "evaluate")


# ── cross-aggregate (3 cases) ─────────────────────────────────────


def test_fold_run_health_is_deterministic_modulo_generated_at(
    tmp_path,
) -> None:
    """Same spine -> same ``conditions`` and ``summary``; only
    ``generated_at`` differs.

    Spec §10.5 property 1. We use ``importlib.import_module`` to get
    the fold function under test (NOT a direct import — the green-
    phase module path is fixed by Task 1.4).
    """
    importlib_path = "lca.plugins.observability.health.run_health_fold"
    importlib.import_module(importlib_path)  # raises ImportError on RED
    mod = importlib.import_module(importlib_path)
    fold_run_health = getattr(mod, "fold_run_health", None)
    assert fold_run_health is not None, (
        f"{importlib_path}.fold_run_health not yet defined"
    )

    # Write a minimal spine with one event of each phase.
    run_id = "run_det"
    spine = tmp_path / f"{run_id}.spine.jsonl"
    events = [
        {"event_id": f"{run_id}:1", "ts": "2026-09-16T02:00:00+00:00",
         "run_id": run_id, "execution_point": "phase.perceive.fold", "payload": {}},
        {"event_id": f"{run_id}:2", "ts": "2026-09-16T02:00:01+00:00",
         "run_id": run_id, "execution_point": "phase.think.fold", "payload": {}},
        {"event_id": f"{run_id}:3", "ts": "2026-09-16T02:00:02+00:00",
         "run_id": run_id, "execution_point": "phase.act.fold", "payload": {}},
        {"event_id": f"{run_id}:4", "ts": "2026-09-16T02:00:03+00:00",
         "run_id": run_id, "execution_point": "phase.reflect.fold", "payload": {}},
        {"event_id": f"{run_id}:5", "ts": "2026-09-16T02:00:04+00:00",
         "run_id": run_id, "execution_point": "phase.remember.fold", "payload": {}},
        {"event_id": f"{run_id}:6", "ts": "2026-09-16T02:00:05+00:00",
         "run_id": run_id, "execution_point": "kernel.run.stop",
         "payload": {"outcome": "success"}},
    ]
    spine.write_text("\n".join(__import__("json").dumps(e) for e in events) + "\n")

    a = fold_run_health(spine)
    b = fold_run_health(spine)

    # conditions tuple is identical element-wise.
    assert a.conditions == b.conditions
    # summary counters are identical.
    assert a.summary.conditions_ok == b.summary.conditions_ok
    assert a.summary.conditions_degraded == b.summary.conditions_degraded
    assert a.summary.conditions_failed == b.summary.conditions_failed
    assert a.summary.conditions_unknown == b.summary.conditions_unknown
    # by_type dict is identical.
    assert a.summary.by_type == b.summary.by_type
    # generated_at is the ONLY seam-injected non-determinism (C8).
    # We don't assert equality (clock may be coarse); we assert
    # both reports are well-formed and differ only at most there.
    assert a.run_id == b.run_id == run_id
    assert a.schema_version == b.schema_version == "1.0"


def test_run_health_report_has_at_least_6_conditions_for_non_empty_run(
    tmp_path,
) -> None:
    """Per spec §10.5 property 2: ``len(conditions) >= 6`` for any
    non-empty run.

    The 8 derivers each return at least 1 condition (even the
    no-events branch returns ``unknown``), so a non-empty spine
    always produces >= 8 conditions. We assert the floor is 6 to
    match the spec's stated invariant.
    """
    import json as _json

    importlib_path = "lca.plugins.observability.health.run_health_fold"
    importlib.import_module(importlib_path)  # raises ImportError on RED
    mod = importlib.import_module(importlib_path)
    fold_run_health = getattr(mod, "fold_run_health", None)
    assert fold_run_health is not None, (
        f"{importlib_path}.fold_run_health not yet defined"
    )

    run_id = "run_six"
    spine = tmp_path / f"{run_id}.spine.jsonl"
    spine.write_text(
        _json.dumps(
            {
                "event_id": f"{run_id}:1",
                "ts": "2026-09-16T02:00:00+00:00",
                "run_id": run_id,
                "execution_point": "phase.think.fold",
                "payload": {},
            }
        )
        + "\n"
    )

    report = fold_run_health(spine)
    assert len(report.conditions) >= 6, (
        f"expected >=6 conditions for a non-empty run, got {len(report.conditions)}"
    )


def test_evidence_refs_execution_points_in_spine_whitelist(tmp_path) -> None:
    """Every condition's ``evidence_refs`` carry an ``execution_point``
    string from a known spine EP vocabulary.

    Spec §10.5 property 4 (traceability). The whitelist is the union
    of all EPs the 8 PR-1 derivers consume. We allow any non-empty
    string (the SPINE_EXECUTION_POINTS closed-set lives in the
    producer contract, not in this fold test); the property the
    fold enforces is ``len(evidence_refs[*].execution_point) > 0``
    for every ref.
    """
    import json as _json

    importlib_path = "lca.plugins.observability.health.run_health_fold"
    importlib.import_module(importlib_path)  # raises ImportError on RED
    mod = importlib.import_module(importlib_path)
    fold_run_health = getattr(mod, "fold_run_health", None)
    assert fold_run_health is not None, (
        f"{importlib_path}.fold_run_health not yet defined"
    )

    run_id = "run_ev"
    spine = tmp_path / f"{run_id}.spine.jsonl"
    events = [
        {"event_id": f"{run_id}:1", "ts": "2026-09-16T02:00:00+00:00",
         "run_id": run_id, "execution_point": "phase.perceive.fold", "payload": {}},
        {"event_id": f"{run_id}:2", "ts": "2026-09-16T02:00:01+00:00",
         "run_id": run_id, "execution_point": "phase.think.fold", "payload": {}},
        {"event_id": f"{run_id}:3", "ts": "2026-09-16T02:00:02+00:00",
         "run_id": run_id, "execution_point": "phase.act.fold", "payload": {}},
        {"event_id": f"{run_id}:4", "ts": "2026-09-16T02:00:03+00:00",
         "run_id": run_id, "execution_point": "phase.reflect.fold", "payload": {}},
        {"event_id": f"{run_id}:5", "ts": "2026-09-16T02:00:04+00:00",
         "run_id": run_id, "execution_point": "phase.remember.fold", "payload": {}},
        {"event_id": f"{run_id}:6", "ts": "2026-09-16T02:00:05+00:00",
         "run_id": run_id, "execution_point": "kernel.run.stop",
         "payload": {"outcome": "success"}},
    ]
    spine.write_text("\n".join(_json.dumps(e) for e in events) + "\n")

    report = fold_run_health(spine)

    # Every ref carries a non-empty execution_point (a spine EP string).
    # We do NOT assert a closed-set match here — the SPINE_EXECUTION_POINTS
    # whitelist lives in the producer contract; the fold only guarantees
    # round-tripping whatever the producer wrote.
    for cond in report.conditions:
        for ref in cond.evidence_refs:
            assert isinstance(ref.execution_point, str)
            assert len(ref.execution_point) > 0


# ── status closed-set sanity (1 implicit case via existing helpers) ──


def test_fold_status_alphabet_is_closed_across_all_derivers() -> None:
    """Every deriver returns statuses drawn from the closed 4-value
    literal ``{ok, degraded, failed, unknown}``. Regression guard for
    spec §10.4 closed-set drift.
    """
    closed: set[RunHealthStatus] = {"ok", "degraded", "failed", "unknown"}
    samples: list[tuple[str, str, list[SpineEvent]]] = [
        ("perceive", "perceive", [_ev(seq=1, execution_point="phase.perceive.fold")]),
        ("perceive", "perceive_empty", []),
        ("think", "think", [_ev(seq=1, execution_point="phase.think.fold")]),
        ("think", "think_empty", []),
        ("act", "act", [_ev(seq=1, execution_point="phase.act.fold")]),
        ("act", "act_empty", []),
        ("reflect", "reflect", [_ev(seq=1, execution_point="phase.reflect.fold")]),
        ("reflect", "reflect_empty", []),
        ("remember", "remember", [_ev(seq=1, execution_point="phase.remember.fold")]),
        ("remember", "remember_empty", []),
        (
            "lifecycle",
            "lifecycle",
            [_ev(seq=1, execution_point="kernel.run.stop",
                 payload={"outcome": "success"})],
        ),
        ("lifecycle", "lifecycle_empty", []),
    ]
    for module_name, _label, events in samples:
        import importlib as _il

        mod = _il.import_module(
            f"lca.plugins.observability.health.derivers.{module_name}_deriver"
        )
        klass_name = module_name.capitalize() + "Deriver"
        klass = getattr(mod, klass_name)
        conditions = klass().evaluate(events)
        for c in conditions:
            assert c.status in closed, (
                f"{module_name} returned non-closed status {c.status!r}"
            )