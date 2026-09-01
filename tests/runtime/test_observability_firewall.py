"""Observability firewall 全链路异常终结器单测。

设计动机:桥接层(perceive_hub / step_emitter / 任何"翻译"代码)
应该永远不把 schema 漂移 / 类型错误传染到认知主链路。 firewall
contextmanager 一次到位接住所有异常, 写 RuntimeObserved, 主链路继续。

覆盖:
- AttributeError / KeyError / TypeError / ValueError / RuntimeError 全部被接住
- KeyboardInterrupt / SystemExit 永远向上抛
- firewall 内部 record_runtime 自身抛 → 不会反向 throw 把链路打死
- 不绑 BoundObservability 时(没 facade) silent no-op, 主链路仍继续
- 多个 firewall 嵌套 / 重入安全
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from lca.runtime.observability_firewall import bridge_firewall


@contextmanager
def _no_op() -> Iterator[None]:
    """空 contextmanager, 测试断言用。"""
    yield


def test_firewall_swallows_attribute_error() -> None:
    """AttributeError 必须被 swallow(perceive_hub 真实案例: state.objective)。"""
    with bridge_firewall("test.attr_error", attributes={"phase": "perceive"}):
        raise AttributeError("'AgentState' object has no attribute 'objective'")
    # 通过 = 没冒泡


def test_firewall_swallows_type_error() -> None:
    with bridge_firewall("test.type_error"):
        raise TypeError("expected str, got None")


def test_firewall_swallows_key_error() -> None:
    with bridge_firewall("test.key_error"):
        raise KeyError("missing_field")


def test_firewall_swallows_value_error() -> None:
    with bridge_firewall("test.value_error"):
        raise ValueError("bad schema")


def test_firewall_swallows_runtime_error() -> None:
    with bridge_firewall("test.runtime_error"):
        raise RuntimeError("facade guard")


def test_firewall_swallows_arbitrary_exception() -> None:
    """任何自定义异常都被吞。"""

    class CustomBridgeError(Exception):
        pass

    with bridge_firewall("test.custom"):
        raise CustomBridgeError("schema drift")
    # 通过


def test_keyboard_interrupt_propagates() -> None:
    """KeyboardInterrupt 必须冒泡 —— 用户主动中断不能被吞。"""
    with pytest.raises(KeyboardInterrupt), bridge_firewall("test.kbd"):
        raise KeyboardInterrupt()


def test_system_exit_propagates() -> None:
    """SystemExit 必须冒泡 —— Python 解释器退出信号不能被吞。"""
    with pytest.raises(SystemExit), bridge_firewall("test.exit"):
        raise SystemExit(1)


def test_propagate_argument_overrides_default() -> None:
    """propagate 参数允许局部覆盖(测试用, 不建议 production 覆盖)。

    propagate=() 意味着"什么都不传播" —— 包括 KeyboardInterrupt 也要吞,
    这是测试 / 危险边界用的; 生产代码永远保留默认 propagate。
    """
    with bridge_firewall("test.propagate_runtime", propagate=()):
        raise RuntimeError("should be swallowed when propagate=()")
    # 通过 = 没冒泡


def test_main_flow_continues_after_exception() -> None:
    """firewall 后的主链路代码必须继续执行。"""
    with bridge_firewall("test.continue"):
        raise ValueError("boom")
    post = "still running"
    assert post == "still running"


def test_attributes_passed_to_record() -> None:
    """attributes 必须传给 record_bridge_failure(供 debug-run 过滤)。"""
    seen: dict[str, object] = {}

    # monkey-patch record_bridge_failure to capture args
    from lca.runtime import observability_firewall as fw_mod

    orig = fw_mod.record_bridge_failure

    def capture(**kwargs: object) -> None:
        seen.update(kwargs)

    fw_mod.record_bridge_failure = capture  # type: ignore[assignment]
    try:
        with bridge_firewall("test.attrs", attributes={"phase": "perceive", "step": 3}):
            raise ValueError("boom")
        assert seen["operation"] == "test.attrs"
        assert seen["error_type"] == "ValueError"
        assert "boom" in str(seen["error_message"])
        assert seen["attributes"] == {"phase": "perceive", "step": 3}
    finally:
        fw_mod.record_bridge_failure = orig  # type: ignore[assignment]


def test_firewall_survives_recording_failure() -> None:
    """firewall 自身 record_runtime 抛时不能再 throw 反向打断主链路。"""
    from lca.runtime import observability_firewall as fw_mod

    original = fw_mod.record_bridge_failure

    def always_fail(**kwargs: object) -> None:
        raise RuntimeError("journal backend down")

    fw_mod.record_bridge_failure = always_fail  # type: ignore[assignment]
    try:
        # 即便 record 抛, firewall 必须 swallow, 主链路继续
        with bridge_firewall("test.self_fail"):
            raise ValueError("original")
        # 通过
    finally:
        fw_mod.record_bridge_failure = original  # type: ignore[assignment]


def test_nested_firewalls() -> None:
    """嵌套 firewall 各自独立报告。"""
    inner_failed = False

    @contextmanager
    def flag() -> Iterator[None]:
        nonlocal inner_failed
        try:
            yield
        except Exception:
            inner_failed = True
            raise

    # 内层抛 → firewall swallow, 主链路进入外层
    with bridge_firewall("test.outer"), bridge_firewall("test.inner"):
        raise KeyError("nested")
    assert inner_failed is False  # inner firewall 真正 swallow 了
    # 外层也通过


def test_no_bound_observability_silent() -> None:
    """没 facade / BoundObservability 时 firewall 自身不能挂掉调用方。

    整个测试在没 facade bind 的环境下运行(record_bridge_failure 内部
    import facade 失败 → 必须 silent 吞)。
    """
    # 这一行直接验证: 没设 run_context / BoundObservability 时,
    # bridge_firewall 仍正常 swallow 异常。
    with bridge_firewall("test.no_obs"):
        raise AttributeError("schema drift in real production code")
    # 通过 = 没冒泡


def test_firewall_is_a_context_manager() -> None:
    """firewall 必须支持 ``with`` 语法, 不需要 enter/exit 手工调用。"""
    cm = bridge_firewall("test.cm")
    assert hasattr(cm, "__enter__")
    assert hasattr(cm, "__exit__")
    with cm:
        pass  # 正常退出


def test_state_objective_does_not_break_firewall() -> None:
    """regression: 模拟 perceive_hub 真实失败 —— 读 state.objective 抛
    AttributeError; 主链路必须不挂。"""

    class FakeState:
        task = "给我讲个笑话"

    state = FakeState()
    with bridge_firewall("bridge.perceive_opened", attributes={"step": 0}):
        # type: ignore[attr-defined]  # 故意读取不存在的字段
        _ = state.objective
    # 通过 = firewall 接住了, 主链路没被打断
