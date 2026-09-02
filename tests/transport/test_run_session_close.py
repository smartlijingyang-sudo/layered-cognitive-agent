"""ADR-0169 PR-12.7:RunSession.close + RunTerminalizer ContextVar token 释放。

PR-1.5 builder 里 ``install_run_cursor`` + PR-12.5 ``install_model_visible_capture``
留了 reset token 给 caller,本 PR 在 RunSession 上加 ``close(reason)`` 方法,
由 RunTerminalizer.terminalize 在 finalize 后调一次,释放两个 ContextVar token,
防止多 run 时 ContextVar 内部字典无限增长(单进程 leak)。

本测试覆盖:
- RunSession.close 一次释放双 token, 二次调用幂等返回 False
- token 为 None 时不抛
- run 结束后再 install_new_token 可以工作(ContextVar 已重置)
"""

from __future__ import annotations

from lca.contracts.observability.incarnation import Incarnation
from lca.infrastructure.observability.loop_cursor import (
    StdLoopCursor,
    install_model_visible_capture,
    install_run_cursor,
    reset_model_visible_capture,
    reset_run_cursor,
)
from lca.infrastructure.observability.loop_cursor.bind import (
    SpineWritePortAdapter,
)
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    get_current_cursor,
)
from lca.infrastructure.observability.loop_cursor.model_visible_binding import (
    get_current_model_visible_capture,
)
from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
    StdModelVisibleCapture,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession


class _StubSpine:
    """EventSpine stub — 仅供 spine.append 调用;并跟踪 append 计数。"""

    def __init__(self) -> None:
        self.appends: list[tuple[str, dict]] = []

    def append(self, **kw: object) -> int:
        # capture kwargs 'execution_point' + 'payload'
        ep = kw.get("execution_point", "")
        payload = kw.get("payload", {})
        self.appends.append((str(ep), dict(payload) if isinstance(payload, dict) else {}))
        return len(self.appends)

    def subscribe(self, *_args: object, **_kw: object) -> None:
        return None

    def close(self) -> None:
        return None


def _build_run_session() -> RunSession:
    """构造最小 RunSession(real dataclass 实例,字段尽量 stub)。"""
    from lca.plugins.transport.webserver.handlers.runs.session.session import (
        RunSession as _RS,  # noqa: N814
    )

    # 直接构造满足 dataclass 必传字段的最小实例
    session = _RS.__new__(_RS)
    # 委托 _closed 在 dataclass init 之后置位
    object.__setattr__(session, "_closed", False)
    return session


def test_session_close_releases_both_tokens(tmp_path) -> None:
    """RunSession.close(Completed) 释放 loop_cursor + model_visible_capture token。"""
    spine = _StubSpine()
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    cursor = StdLoopCursor(
        spine=SpineWritePortAdapter(spine),
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="default", incarnation_seq=1),
    )
    cursor_token = install_run_cursor(cursor)
    capture = StdModelVisibleCapture(run_dir=run_dir)
    capture_token = install_model_visible_capture(capture)

    session = _build_run_session()
    session.loop_cursor = cursor
    session.loop_cursor_token = cursor_token
    session.model_visible_capture = capture
    session.model_visible_capture_token = capture_token

    # 装上后 ContextVar 都生效
    assert get_current_cursor() is cursor
    assert get_current_model_visible_capture() is capture

    # 第一次 close
    released = session.close("completed")
    assert released is True

    # token 字段已清空
    assert session.loop_cursor_token is None
    assert session.model_visible_capture_token is None
    # ContextVar 已 reset;现在 ``get_current_*`` 应返回 None(默认)
    assert get_current_cursor() is None
    assert get_current_model_visible_capture() is None


def test_session_close_is_idempotent(tmp_path) -> None:
    """第二次 close 返回 False,不抛。"""
    session = _build_run_session()
    session.loop_cursor_token = None
    session.model_visible_capture_token = None

    assert session.close("completed") is True
    assert session.close("error") is False  # idempotent
    assert session.close("completed") is False


def test_session_close_with_none_tokens_is_safe() -> None:
    """token 字段全 None(测试场景 builder 未装 token)close 仍 True 不抛。"""
    session = _build_run_session()
    assert session.close("completed") is True


def test_close_resets_context_allowing_new_install(tmp_path) -> None:
    """close 后,新 run 可以 install_run_cursor / install_model_visible_capture。"""
    spine = _StubSpine()
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    session = _build_run_session()
    cursor1 = StdLoopCursor(
        spine=SpineWritePortAdapter(spine),
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="default", incarnation_seq=1),
    )
    token1 = install_run_cursor(cursor1)
    capture1 = StdModelVisibleCapture(run_dir=run_dir / "1")
    token2 = install_model_visible_capture(capture1)
    session.loop_cursor = cursor1
    session.loop_cursor_token = token1
    session.model_visible_capture = capture1
    session.model_visible_capture_token = token2

    session.close("completed")

    # close 后 install 第二个 run — 不抛 ValueError (Token not from this ContextVar)
    cursor2 = StdLoopCursor(
        spine=SpineWritePortAdapter(spine),
        run_id="r2",
        trace_id="t2",
        incarnation=Incarnation(run_id="r2", plan_ref="default", incarnation_seq=1),
    )
    token3 = install_run_cursor(cursor2)
    capture2 = StdModelVisibleCapture(run_dir=run_dir / "2")
    token4 = install_model_visible_capture(capture2)
    try:
        assert get_current_cursor() is cursor2
        assert get_current_model_visible_capture() is capture2
    finally:
        reset_run_cursor(token3)
        reset_model_visible_capture(token4)
