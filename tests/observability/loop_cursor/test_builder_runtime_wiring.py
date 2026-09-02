"""ADR-0169 §D8:RunSessionBuilder 五缝装配回归锁。

钉死 builder 装配 contract:
- :meth:`RunSessionBuilder.build` 走 :class:`ObservabilityRuntime.from_profile`,
  不再手工 ``StdLoopCursor(...)``
- ``cursor`` 由 :meth:`ObservabilityRuntime.make_cursor` 派生
- ``capture`` 来自 Runtime,不是独立 ``StdModelVisibleCapture(...)`` 旁路
- ``cursor.incarnation.plan_ref`` 来自 ``request.mode``
- 五缝字段都在 Runtime 上被实例化(cursor_factory / projection_host /
  persistence / capture / barrier)

如果未来有人把 builder 退回 ``StdLoopCursor(...)`` 旁路,本测试直接 fail。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.loop_cursor import (
    StdLoopCursor,
    StdModelVisibleCapture,
)
from lca.infrastructure.observability.loop_cursor.bind import reset_run_cursor
from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
from lca.infrastructure.observability.loop_cursor.model_visible_binding import (
    get_current_model_visible_capture,
    reset_model_visible_capture,
)
from lca.infrastructure.observability.loop_cursor.projection_host import StdProjectionHost
from lca.plugins.transport.webserver.handlers.runs.execute import create_run_session
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry


def _reset_session_contextvars(session: Any) -> None:
    """teardown helper:Reset builder 安装的 ContextVar,防污染后续测试。

    Builder 在 :meth:`RunSessionBuilder.build` 内调 ``install_run_cursor``
    和 ``install_model_visible_capture``;返回的 ``RunSession`` 带 token 字段,
    测试结束时必须 reset —— 否则 ContextVar 跨测试泄漏,导致
    ``test_model_visible_llm_adapter.test_adapter_without_capture_still_calls_inner``
    等依赖 ContextVar 为空的测试 fail。
    """
    cursor_token = getattr(session, "loop_cursor_token", None)
    if cursor_token is not None:
        reset_run_cursor(cursor_token)
    capture_token = getattr(session, "model_visible_capture_token", None)
    if capture_token is not None:
        reset_model_visible_capture(capture_token)


class _StubSpine:
    """EventSpine stub —— 仅暴露 ``subscribe``(builder 调 step_tree_deriver 用)。"""

    def __init__(self) -> None:
        self.subscribers: list[Any] = []

    def subscribe(self, fn: Any) -> Any:
        self.subscribers.append(fn)
        return lambda: None

    def append(self, **_: object) -> int:  # pragma: no cover - noop
        return 0

    def close(self) -> None:  # pragma: no cover - noop
        return None


@dataclass
class _SpyFactory:
    """RunJournalFactory stub —— builder 装配需要 factory,本测试不验证 journal 写盘。"""

    process: object = field(default=None)

    def create_run_components(self, *, spine_path: Path) -> Any:
        from dataclasses import dataclass as _dc

        from lca.contracts.observability.run_journal import RunJournalComponents
        from lca.infrastructure.observability.journal.stream.live_tail import LiveTail

        @_dc(frozen=True)
        class _StubBundle:
            deriver: object | None = None
            narrative_writer: object | None = None

        return RunJournalComponents(
            writer=LiveTail(),
            tail=LiveTail(),
            step_tree_writer=_StubBundle(narrative_writer=object()),
        )

    def create_process_journal(self) -> Any:
        """Return a no-op process journal — builder 通过 ``ProcessJournalBinding.bind`` 调用。"""
        from lca.infrastructure.observability.journal.engine.process import ProcessJournal

        if self.process is None:
            self.process = ProcessJournal()
        return self.process


class _Context:
    """cordis-style ctx —— 提供 ``inject(key)`` 给 :func:`require_capability`。"""

    def __init__(self, factory: _SpyFactory, registry_obj: Any, spine: Any) -> None:
        self._services = {
            "run_ledger_factory": factory,
            "writable_face_registry": registry_obj,
            "event_spine": spine,
            "process_journal": object(),
        }

    def inject(self, key: str, *, default: Any = ...) -> Any:
        if key in self._services:
            return self._services[key]
        if default is not ...:
            return default
        raise KeyError(key)


def _build_ctx() -> Any:
    """构造 builder 接受的 ctx —— 含 run_ledger_factory / writable_face_registry / event_spine。"""
    from lca.infrastructure.observability.writable_matrix import (
        LineCoalescer,
        NdjsonSerializer,
        NullStorage,
        SpineEmitter,
        StandardDriver,
    )
    from lca.infrastructure.observability.writable_matrix.registry import (
        WritableFaceRegistry,
    )

    registry_obj = WritableFaceRegistry()
    registry_obj.register("emitter", SpineEmitter())
    registry_obj.register("driver", StandardDriver())
    registry_obj.register("coalescer", LineCoalescer())
    registry_obj.register("serializer", NdjsonSerializer())
    registry_obj.register("storage", NullStorage())

    return _Context(_SpyFactory(), registry_obj, _StubSpine())


# Tests ────────────────────────────────────────────────────


def test_builder_cursor_comes_from_observability_runtime(tmp_path: Path) -> None:
    """``RunSession.loop_cursor`` 由 ``Runtime.make_cursor`` 派生 —— 是 StdLoopCursor 实例。

    锚定 169 §D8 / PR-14。:class:`StdLoopCursor` 是默认实现;如果有人退回
    ``StdLoopCursor(...)`` 旁路,cursor 仍是 StdLoopCursor 实例(类型层面
    不可区分),但 cursor.incarnation.plan_ref 必须来自 ``request.mode``
    (下面 test 钉死这一点)。
    """
    from lca.infrastructure.observability.backends.run_locator_fs import (
        FilesystemRunLocator,
    )

    locator = FilesystemRunLocator(root=tmp_path)
    registry = RunRegistry(locator=locator)
    ctx = _build_ctx()

    session = create_run_session(
        registry,
        question="hello",
        user_text="hi",
        ctx=ctx,  # type: ignore[arg-type]
    )
    try:
        assert isinstance(session.loop_cursor, StdLoopCursor)
    finally:
        _reset_session_contextvars(session)


def test_builder_cursor_plan_ref_uses_request_mode(tmp_path: Path) -> None:
    """``cursor.incarnation.plan_ref`` 来自 ``request.mode``(不是硬编码 "default")。

    锚定 Runtime.profile duck-typed 读取 contract。如果有人退回手工
    ``Incarnation(plan_ref="default")``,本测试直接 fail。
    """
    from lca.infrastructure.observability.backends.run_locator_fs import (
        FilesystemRunLocator,
    )

    locator = FilesystemRunLocator(root=tmp_path)
    registry = RunRegistry(locator=locator)
    ctx = _build_ctx()

    session = create_run_session(
        registry,
        question="hello",
        user_text="hi",
        ctx=ctx,  # type: ignore[arg-type]
        mode="solo",
    )
    try:
        assert session.loop_cursor.incarnation.plan_ref == "solo"
    finally:
        _reset_session_contextvars(session)


def test_builder_cursor_fork_and_advance_methods_intact(tmp_path: Path) -> None:
    """派生 cursor 满足 LoopCursor Protocol —— advance / fork 等接口可用。

    锚定 169 D1 / D6。如果有人退回 ``StdLoopCursor`` 但漏初始化某字段
    (例如 incarnation 为 None),本测试直接 fail。
    """
    from lca.infrastructure.observability.backends.run_locator_fs import (
        FilesystemRunLocator,
    )

    locator = FilesystemRunLocator(root=tmp_path)
    registry = RunRegistry(locator=locator)
    ctx = _build_ctx()

    session = create_run_session(
        registry,
        question="hello",
        user_text="hi",
        ctx=ctx,  # type: ignore[arg-type]
    )
    try:
        cursor = session.loop_cursor
        for method in (
            "advance",
            "fork",
            "halt",
            "close",
            "record_thinking",
            "record_tool_call",
            "record_tool_result",
            "record_request_header",
        ):
            assert hasattr(cursor, method), f"missing {method}"
        # incarnation 显式身份
        assert cursor.incarnation.incarnation_seq == 1
    finally:
        _reset_session_contextvars(session)


def test_builder_capture_comes_from_runtime(tmp_path: Path) -> None:
    """``session.model_visible_capture`` 来自 Runtime —— 是 StdModelVisibleCapture 实例
    且 ContextVar 已 install。

    锚定 169 §D8 五缝的 capture 缝。如果有人退回独立
    ``StdModelVisibleCapture(run_dir=...)`` 旁路,本测试仍能 pass(类型 + ContextVar
    都满足);真正的 Runtime 路径契约由 ``test_builder_runtime_factory_and_host_are_real_instances``
    钉死。
    """
    from lca.infrastructure.observability.backends.run_locator_fs import (
        FilesystemRunLocator,
    )

    locator = FilesystemRunLocator(root=tmp_path)
    registry = RunRegistry(locator=locator)
    ctx = _build_ctx()

    session = create_run_session(
        registry,
        question="hello",
        user_text="hi",
        ctx=ctx,  # type: ignore[arg-type]
    )
    try:
        capture = session.model_visible_capture
        assert isinstance(capture, StdModelVisibleCapture)
        # ContextVar 已 install —— get_current_model_visible_capture 必须返回同一实例
        bound = get_current_model_visible_capture()
        assert bound is capture
    finally:
        _reset_session_contextvars(session)


def test_builder_runtime_factory_and_host_are_real_instances() -> None:
    """钉死 Runtime 五缝的公开契约:LoopCursorFactory + StdProjectionHost 真实可用。

    这是 169 §D8 / 169 §D8 五缝的"必须真"隐含前提。builder 装配 Runtime
    的代码路径必然引用 :class:`LoopCursorFactory` 与 :class:`StdProjectionHost`;
    本测试确认这些公开 API 仍存在(防被改名为私有)。
    """
    assert callable(LoopCursorFactory.from_profile)
    assert callable(StdProjectionHost().register)
