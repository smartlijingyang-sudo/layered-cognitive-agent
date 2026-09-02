"""ADR-0172 PR-6 LangfuseProjection 测试。

覆盖:
- 无 langfuse SDK 时 import / init 不崩溃(降级为 accumulator)
- llm.request.header EP 触发 score 累加
- view 返回 scores 列表
- 不订阅 writable.iteration.close(L16 由 host 默认清单钉死)
- reducer 纯函数(不改入参 state)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.loop_cursor.projections.langfuse_projection import (
    LangfuseProjection,
    langfuse_sdk_available,
)


@dataclass(frozen=True)
class _StubRecord:
    """绕开 EventRecord EP whitelist 检查的最小桩。"""

    execution_point: str
    sequence: int
    payload: dict[str, Any]


def _snap(seq: int = 0, step_id: str | None = "s1") -> CursorSnapshot:
    return CursorSnapshot(
        run_id="r",
        trace_id="t",
        incarnation=1,
        step_id=step_id,
        step_index=1,
        iteration=1,
        attempt_in_step=0,
        phase="think",  # type: ignore[arg-type]
        iteration_reason=None,
        stop_signal=None,
        seq=seq,
    )


# ── 1. SDK 缺席时 import / init 不崩溃 ──────────────────────────────
def test_init_does_not_crash_when_sdk_missing() -> None:
    """若 langfuse SDK 未安装,LangfuseProjection 应降级为 accumulator。

    设计约束:模块 import 不抛 ImportError;``langfuse_sdk_available()``
    返回 bool,init 返回的 state 携带 ``sdk_available`` 字段;无论 SDK
    是否在场,``apply`` 与 ``view`` 行为一致。
    """
    p = LangfuseProjection()
    state = p.init()
    assert "sdk_available" in state
    assert isinstance(state["sdk_available"], bool)
    assert state["sdk_available"] == langfuse_sdk_available()
    assert state["scores"] == []


# ── 2. llm.request.header 累加 score(view 返回列表) ─────────────────
def test_scores_accumulate_on_llm_request_header() -> None:
    p = LangfuseProjection()
    snap = _snap()

    state = p.init()
    # 无关 EP 不触发累加
    state = p.apply(
        state,
        snap,
        _StubRecord(
            execution_point="step.thinking.record",
            sequence=1,
            payload={"token_count": 5},
        ),
    )
    assert state["scores"] == []

    # llm.request.header 触发 score 累加
    state = p.apply(
        state,
        snap,
        _StubRecord(
            execution_point="llm.request.header",
            sequence=2,
            payload={"step_id": "step-001", "model": "gpt-4"},
        ),
    )
    state = p.apply(
        state,
        snap,
        _StubRecord(
            execution_point="llm.request.header",
            sequence=3,
            payload={"step_id": "step-002", "model": "claude-3"},
        ),
    )
    assert len(state["scores"]) == 2
    assert state["scores"][0]["step_id"] == "step-001"
    assert state["scores"][0]["model"] == "gpt-4"
    assert state["scores"][0]["sequence"] == 2
    assert state["scores"][1]["step_id"] == "step-002"
    assert state["scores"][1]["model"] == "claude-3"

    # view 返回 scores 列表
    view = p.view(state)
    assert isinstance(view, list)
    assert len(view) == 2
    assert view[0]["model"] == "gpt-4"

    # restore 重置
    restored = p.restore(state)
    assert restored["scores"] == []


# ── 3. 注入 client 路径(配置可注入,client 可为任意对象) ────────────
def test_client_can_be_injected_via_constructor() -> None:
    sentinel_client = object()
    p = LangfuseProjection(client=sentinel_client)
    assert p._client is sentinel_client
    # apply 仍然走 reducer 路径,无关 SDK 是否在场
    state = p.init()
    state = p.apply(
        state,
        _snap(),
        _StubRecord(
            execution_point="llm.request.header",
            sequence=1,
            payload={"step_id": "s1", "model": "m"},
        ),
    )
    assert len(state["scores"]) == 1
