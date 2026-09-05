"""TokenUsageUnit 投影 + 冷/热 fold 等价（验收 #14）。"""

from __future__ import annotations

from lca.plugins.session.projection_registry.projection_registry import ProjectionRegistry
from lca.plugins.session.runtime.session import Session
from lca.plugins.session.token_meter.token_meter import HeuristicTokenMeter
from lca.plugins.session.token_usage.token_usage import TokenUsageUnit
from lca_kernel.events.fold import SURFACE_ASSISTANT_TYPE, SURFACE_USER_TYPE, foldRequestHeader
from lca_kernel.events.session import SESSION_FORMAT_VERSION, SessionHeader


def _sample_session() -> Session:
    session = Session("tok_1")
    session.append(
        SURFACE_USER_TYPE,
        {"content": "hello world"},
        surface_op="append",
    )
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "hi there"}},
        surface_op="append",
    )
    session.append("model.completed.v1", {"turn": 1, "step": 1, "usage": {"total_tokens": 42}})
    return session


def test_projection_hot_snapshot_matches_meter() -> None:
    session = _sample_session()
    registry = ProjectionRegistry()
    unit = TokenUsageUnit()
    registry.register(unit)
    registry.register_to(session)

    hot_view = registry.snapshot(session).values["token_usage"]
    header_fold = foldRequestHeader(session.snapshot_events())
    assert header_fold is not None
    header = {
        "config": dict(header_fold.config or {}),
        "system": header_fold.system,
        "tools": list(header_fold.tools or ()),
    }
    meter = HeuristicTokenMeter().measure(session, header=header)
    assert hot_view["surface_tokens"] == meter.surface_tokens
    assert hot_view["baseline"] == meter.baseline
    assert hot_view["total_tokens"] == meter.total_tokens


def test_projection_cold_restore_matches_hot_snapshot() -> None:
    session = _sample_session()
    registry = ProjectionRegistry()
    unit = TokenUsageUnit()
    registry.register(unit)
    registry.register_to(session)
    hot = registry.snapshot(session).values["token_usage"]
    checkpoint = registry.checkpoint(session)

    cold_registry = ProjectionRegistry()
    cold_registry.register(unit)
    restored = cold_registry.restore(
        checkpoint,
        session.snapshot_events(),
        SessionHeader(version=SESSION_FORMAT_VERSION, id="tok_1", created_at=0),
    )
    cold = restored.snapshot.values["token_usage"]

    assert cold["surface_tokens"] == hot["surface_tokens"]
    assert cold["baseline"] == hot["baseline"]
    assert cold["total_tokens"] == hot["total_tokens"]
    assert cold["log_revision"] == hot["log_revision"]
