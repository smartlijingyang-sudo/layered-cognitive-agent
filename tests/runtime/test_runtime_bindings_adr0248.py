"""ADR-0248 运行时绑定回填 seam 测试。

验证 ``with_runtime_bindings`` 在每 Run 启动后把声带/审查/身份字段回填到
当前 ``BindingsViewBuilder``，并在 run 结束后 reset 回前值（ContextVar
嵌套语义不泄漏）。
"""

from __future__ import annotations

from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    current_bindings_view,
    reset_capability_bindings,
    set_capability_bindings,
    with_runtime_bindings,
)


def test_builder_defaults_adr0248_fields() -> None:
    builder = BindingsViewBuilder()
    view = builder.build()
    assert view.vocal_mode == "direct"
    assert view.vocal_gate is None
    assert view.auto_review_mode == "off"
    assert view.auto_review_gate is None
    assert view.origin == "user"
    assert view.box_accessor is None


def test_with_runtime_bindings_republishes_typed_view() -> None:
    base = BindingsViewBuilder(file_store=object(), mode="team")
    outer = set_capability_bindings(base)
    gate = object()
    box = object()
    token = with_runtime_bindings(
        vocal_mode="gated",
        vocal_gate=gate,
        auto_review_mode="enforce",
        auto_review_gate=object(),
        origin="subagent",
        box_accessor=box,
    )
    try:
        view = current_bindings_view()
        assert view is not None
        assert view.vocal_mode == "gated"
        assert view.vocal_gate is gate
        assert view.auto_review_mode == "enforce"
        assert view.origin == "subagent"
        assert view.box_accessor is box
        # 非覆盖字段保持前值
        assert view.mode == "team"
        assert view.file_store is base.file_store
    finally:
        reset_capability_bindings(token)
        view = current_bindings_view()
        assert view is not None
        assert view.vocal_mode == "direct"
    reset_capability_bindings(outer)


def test_with_runtime_bindings_without_active_builder_creates_one() -> None:
    token = with_runtime_bindings(origin="subagent")
    try:
        view = current_bindings_view()
        assert view is not None
        assert view.origin == "subagent"
    finally:
        reset_capability_bindings(token)
    assert current_bindings_view() is None
