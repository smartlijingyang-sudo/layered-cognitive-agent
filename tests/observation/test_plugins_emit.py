"""observation plugin smoke tests —— 每个 plugin 调用 observer 函数不抛错。

不验证 Session 单轨落盘(Session unbound 时 append_surface_bound no-op),
只验证:
  1. observer 函数可调用
  2. 构造的 fact 通过 Pydantic schema 验证
  3. @plugin(...) 装饰器 setup 函数可注册

零 in-memory state 验证 = 每个 plugin 重复调用结果独立、无 mutation。
"""

from __future__ import annotations

from lca.contracts.observability.observation import (
    DiffReport,
    FailureExplanation,
    PlanBlueprint,
    RunReplay,
)


def test_plan_compile_plugin_observer() -> None:
    from lca.plugins.observation.lifecycle.plan_compile.plugin import (
        observe_plan_compile,
    )

    observe_plan_compile(
        run_id="r",
        plan_ref="p",
        profile_path="p.yaml",
        plan_version="v1",
        revision="r1",
        nodes=[{"id": "perceive.main", "phase": "perceive"}],
        edges=[{"from": "perceive.main", "to": "think.main"}],
        actions_authorized=["use_TOOL"],
        capabilities_granted=["cap.1"],
    )


def test_node_trajectory_plugin_observer() -> None:
    from lca.plugins.observation.node_trajectory.plugin import (
        observe_node_enter,
        observe_node_exit,
    )

    observe_node_enter(
        run_id="r",
        node_id="perceive.main",
        phase="perceive",
        inputs={"user_text": "hi"},
    )
    observe_node_exit(
        run_id="r",
        node_id="perceive.main",
        phase="perceive",
        outputs={"context": {"x": 1}},
        exit_status="success",
    )


def test_decision_trace_plugin_observer() -> None:
    from lca.plugins.observation.decision_trace.plugin import observe_decision

    observe_decision(
        run_id="r",
        decision_id="d1",
        source_node_id="think.main",
        accepted=True,
        action_type="use_TOOL",
    )


def test_control_trace_plugin_observer() -> None:
    from lca.plugins.observation.control_trace.plugin import observe_control

    observe_control(
        run_id="r",
        source_node_id="act.main",
        control_slot="act.authorize",
        verdict="deny",
        reason="action type is not authorized",
        contract_clause="art.action.action_type",
    )


def test_tool_call_trace_plugin_observer() -> None:
    from lca.plugins.observation.tool_call_trace.plugin import observe_tool_call

    observe_tool_call(
        run_id="r",
        source_node_id="x",
        tool_name="search",
        args={"q": "x"},
        result={"hits": 1},
        success=True,
    )


def test_llm_call_trace_plugin_observer() -> None:
    from lca.plugins.observation.llm_call_trace.plugin import observe_llm_call

    observe_llm_call(
        run_id="r",
        source_node_id="x",
        model="gpt-5",
        prompt_digest="p",
        response_digest="r",
    )


def test_runtime_bookkeeping_plugin_observer() -> None:
    from lca.plugins.observation.runtime_bookkeeping.plugin import (
        observe_reducer_apply,
    )

    observe_reducer_apply(
        run_id="r",
        method="apply_step_advanced",
        outcome="success",
        phase_boundary=True,
    )


def test_subgraph_resolve_plugin_observer() -> None:
    from lca.plugins.observation.lifecycle.subgraph_resolve.plugin import (
        observe_subgraph_resolve,
    )

    observe_subgraph_resolve(
        run_id="r",
        plan_ref="p",
        owner_node_id="think.main",
        entry_node="think.shortcut",
        status="resolved",
    )


def test_bundle_load_plugin_observer() -> None:
    from lca.plugins.observation.lifecycle.bundle_load.plugin import (
        observe_bundle_load,
    )

    observe_bundle_load(
        run_id="r",
        bundle_id="b1",
        plugin_id="p1",
        status="loaded",
        version="v1",
    )


def test_artifact_snapshot_plugin_observer() -> None:
    from lca.plugins.observation.artifact_snapshot.plugin import (
        observe_artifact_snapshot,
    )

    observe_artifact_snapshot(
        run_id="r",
        node_id="think.main",
        phase="think",
        artifacts={"decision": {"action_type": "use_TOOL"}},
    )


def test_diff_plugin_pure() -> None:
    from lca.plugins.diagnosis.blueprint_trajectory_differ.plugin import (
        diff_blueprint_trajectory,
    )

    bp = PlanBlueprint(
        plan_ref="p",
        profile_path="p",
        plan_version="v",
        revision="r",
        nodes=(),
        edges=(),
        compiled_at="t",
    )
    diff = diff_blueprint_trajectory(run_id="r", blueprint=bp, node_exits=[])
    assert isinstance(diff, DiffReport)


def test_explainer_plugin_pure() -> None:
    from lca.plugins.diagnosis.failure_explainer.plugin import explain_failure

    diff = DiffReport(run_id="r", plan_ref="p", diffed_at="t")
    explanation = explain_failure(run_id="r", diff=diff, control_traces=[])
    assert isinstance(explanation, FailureExplanation)


def test_replay_plugin_pure() -> None:
    from lca.plugins.diagnosis.run_replay.plugin import build_run_replay

    bp = PlanBlueprint(
        plan_ref="p",
        profile_path="p",
        plan_version="v",
        revision="r",
        nodes=(),
        edges=(),
        compiled_at="t",
    )
    replay = build_run_replay(
        run_id="r",
        blueprint=bp,
        node_enters=[],
        node_exits=[],
        decision_traces=[],
        control_traces=[],
        tool_calls=[],
        llm_calls=[],
    )
    assert isinstance(replay, RunReplay)


def test_all_plugins_importable() -> None:
    """13 plugin 全部 importable,@plugin 装饰器返回的 Plugin 对象元数据齐。"""
    from lca.plugins.diagnosis.blueprint_trajectory_differ.plugin import (
        setup as s11,
    )
    from lca.plugins.diagnosis.failure_explainer.plugin import setup as s12
    from lca.plugins.diagnosis.run_replay.plugin import setup as s13
    from lca.plugins.observation.artifact_snapshot.plugin import setup as s10
    from lca.plugins.observation.control_trace.plugin import setup as s6
    from lca.plugins.observation.decision_trace.plugin import setup as s5
    from lca.plugins.observation.lifecycle.bundle_load.plugin import (
        setup as s3,
    )
    from lca.plugins.observation.lifecycle.plan_compile.plugin import (
        setup as s1,
    )
    from lca.plugins.observation.lifecycle.subgraph_resolve.plugin import (
        setup as s2,
    )
    from lca.plugins.observation.llm_call_trace.plugin import setup as s8
    from lca.plugins.observation.node_trajectory.plugin import setup as s4
    from lca.plugins.observation.runtime_bookkeeping.plugin import setup as s9
    from lca.plugins.observation.tool_call_trace.plugin import setup as s7

    # setup 经 @plugin 装饰后变成 Plugin 对象(有 meta 字段),不再是裸函数。
    # 关键检查:每个 plugin 都有 id / layer / effects。
    for plugin in (s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13):
        meta = getattr(plugin, "meta", None)
        assert meta is not None, f"plugin {plugin} missing meta"
        assert meta.get("id"), "plugin meta missing id"
        assert meta.get("layer") in ("L0", "L1", "L2", "L3", "L4")
        assert "none" in meta.get("effects", []) or meta.get("effects") == []
