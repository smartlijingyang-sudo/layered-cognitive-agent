"""Plugin shape 校验 — gate.multi-tool-loop-breaker 满足 ADR-0214 PR-B contract.

按 AGENTS.md §5 "Plugin 硬约束":
- 每个 plugin 一个 .py 文件
- @plugin(...) 为唯一入口
- effects 必声明
- setup() 只能调 Manifest 声明的 provide/require/register/emit
- Plugin 间禁止直接 import;只通过 capability key 交互
"""

from __future__ import annotations

from lca.contracts.protocols import DecisionGate


def _plugin_obj():
    """Load the Cordis Plugin object produced by the @plugin decorator."""
    from lca.plugins.cognitive.gate.multi_tool_loop_breaker import plugin

    return plugin.setup


def test_plugin_import_loads():
    """plugin 模块能 import,装饰器 @plugin 返回 CordisPlugin 对象。"""
    from lca.plugins.cognitive.gate.multi_tool_loop_breaker import plugin

    p = plugin.setup
    assert p is not None
    assert callable(p.setup)  # underlying setup fn
    assert p.name == "gate.multi-tool-loop-breaker"


def test_plugin_id_is_unique():
    """plugin id 命名空间 + 版本号明确。"""
    p = _plugin_obj()
    assert p.name == "gate.multi-tool-loop-breaker"
    assert p.meta["id"] == "gate.multi-tool-loop-breaker"


def test_plugin_effects_declared_as_none():
    """Multi-tool breaker 不引入新 effect (与 single-tool breaker 对齐)。"""
    p = _plugin_obj()
    effects = p.meta.get("effects", [])
    assert "none" in effects, f"plugin effects 应声明 none, 实为 {effects!r}"


def test_plugin_declares_required_capabilities():
    """plugin 必须显式声明 requires / provides (AGENTS.md §5)。"""
    p = _plugin_obj()
    assert "gates" in p.inject
    assert "loop_guard_policy" in p.inject
    assert "DecisionGate" in p.meta["implements"]


def test_plugin_test_suite_path_declared():
    """plugin 必须声明 test_suite 路径(AGENTS.md §5 Plugin 硬约束)。"""
    p = _plugin_obj()
    assert p.meta.get("test_suite") == ("tests/cognition/test_multi_tool_loop_breaker.py")


def test_plugin_setup_body_has_no_global_side_effects():
    """setup body 不能读 env / 写文件 / 跑 subprocess (AGENTS.md §5)。"""
    import inspect

    p = _plugin_obj()
    source = inspect.getsource(p.setup)
    forbidden = ["os.environ", "open(", "subprocess.", "requests."]
    for token in forbidden:
        assert token not in source, (
            f"plugin setup 出现禁止副作用 token {token!r},违反 C5 / AGENTS.md §5"
        )


def test_no_direct_import_of_other_plugins():
    """plugin 间禁止直接 import (AGENTS.md §5);只通过 capability key 交互。"""
    import inspect

    from lca.plugins.cognitive.gate.multi_tool_loop_breaker import plugin as mod

    source = inspect.getsource(mod)
    forbidden = [
        "from lca.plugins.cognitive.gate.tool_loop_breaker",
        "import lca.plugins.cognitive.gate.tool_loop_breaker",
        "from lca.plugins.cognitive.gate.progress_loop_detector",
        "import lca.plugins.cognitive.gate.progress_loop_detector",
    ]
    for token in forbidden:
        assert token not in source, (
            f"plugin 模块直接 import 其他 plugin {token!r},违反 AGENTS.md §5"
        )


def test_gate_implements_decision_gate_protocol():
    """MultiToolLoopBreakerGate 实现 DecisionGate 协议。"""
    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        MultiToolLoopBreakerGate,
    )
    from lca.contracts.models.core.policy.loop_policy import DEFAULT_LOOP_POLICY

    gate = MultiToolLoopBreakerGate(thresholds=DEFAULT_LOOP_POLICY)
    assert isinstance(gate, DecisionGate)
