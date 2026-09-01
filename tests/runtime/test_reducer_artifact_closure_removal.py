"""ADR-0158 commit 1 + 2:reducer.apply_artifact_closure 整段删除 + Protocol 同步。

约束(ADR-0070 C4 Reducer 不私改 status / ADR-0077 TerminalOutcome sole truth):

- DefaultReducer 不再有 apply_artifact_closure 方法
- Reducer Protocol 不再有 apply_artifact_closure 抽象方法
- finalizer 不再调 apply_artifact_closure
- ArtifactClosureDeltaHandler 类删除(closure 走 transport projection 通道,
  不再经 reducer 流)
- delta_handler_registry 移除 artifact_closure 注册项
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.state.reducer import Reducer
from lca.runtime.reducer import DefaultReducer


def _state() -> AgentState:
    return AgentState(
        trace_id="t-1",
        budget=Budget(),
        working_memory={},
        history=[],
    )


def test_default_reducer_does_not_have_apply_artifact_closure() -> None:
    """ADR-0158 决策 六:apply_artifact_closure 整段删除。"""

    reducer = DefaultReducer()
    assert not hasattr(reducer, "apply_artifact_closure"), (
        "DefaultReducer.apply_artifact_closure 必须被删除 "
        "(ADR-0158 决策 六;closure 改走 transport projection 通道)"
    )


def test_reducer_protocol_does_not_declare_apply_artifact_closure() -> None:
    """Reducer Protocol 同步删除 apply_artifact_closure 抽象方法。"""

    assert not hasattr(Reducer, "apply_artifact_closure"), (
        "Reducer Protocol 不应再声明 apply_artifact_closure "
        "(ADR-0158 决策 六)"
    )


def test_finalizer_does_not_call_apply_artifact_closure() -> None:
    """finalizer 不再调 apply_artifact_closure(已迁出 reducer 流)。"""

    from lca.runtime import result_finalizer

    src = result_finalizer.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    assert "apply_artifact_closure" not in body, (
        "result_finalizer.py 仍含 apply_artifact_closure 调用 "
        "(ADR-0158 决策 二)"
    )


def test_artifact_closure_delta_handler_class_deleted() -> None:
    """ArtifactClosureDeltaHandler 类删除(走 transport 投影通道)。"""

    try:
        from lca.plugins.providers.act.delta_handlers import ArtifactClosureDeltaHandler  # type: ignore[attr-defined]

        exists = True
    except ImportError:
        exists = False
    assert not exists, (
        "ArtifactClosureDeltaHandler 必须删除 "
        "(ADR-0158 决策 二:closure 改走 transport projection 通道)"
    )


def test_delta_handler_registry_does_not_register_artifact_closure() -> None:
    """delta_handler_registry 不再注册 artifact_closure handler。"""

    from lca.plugins.providers.act import delta_handler_registry

    src = delta_handler_registry.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    assert "ArtifactClosureDeltaHandler" not in body, (
        "delta_handler_registry 仍含 ArtifactClosureDeltaHandler 注册 "
        "(ADR-0158 决策 二)"
    )