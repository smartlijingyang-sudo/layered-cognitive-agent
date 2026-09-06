"""Model-visible projection read path tests (ADR-0193 I-MV-PROJ-1)."""

from __future__ import annotations

from lca.plugins.session.projection_registry.projection_registry import ProjectionRegistry
from lca.plugins.session.runtime.messages.messages import derive_messages
from lca.plugins.session.runtime.projection.projection_reader import model_visible_messages
from lca.session.append import Session
from lca.plugins.session.session_model_visible.session_model_visible import ModelVisibleUnit
from lca_kernel.events.fold.fold import SURFACE_ASSISTANT_TYPE, SURFACE_USER_TYPE


def _registry_with_model_visible() -> ProjectionRegistry:
    registry = ProjectionRegistry()
    registry.register(ModelVisibleUnit())
    return registry


def test_projection_matches_derive_messages_append_only() -> None:
    registry = _registry_with_model_visible()
    session = Session("mv_parity_1")
    registry.register_to(session)
    session.append(SURFACE_USER_TYPE, {"content": "hi"}, surface_op="append")
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "hello"}},
        surface_op="append",
    )
    expected = derive_messages(session.snapshot_events())
    assert model_visible_messages(session) == expected
    assert session.derive_messages() == expected


def test_projection_matches_derive_messages_replace() -> None:
    registry = _registry_with_model_visible()
    session = Session("mv_parity_2")
    registry.register_to(session)
    session.append(SURFACE_USER_TYPE, {"content": "a"}, surface_op="append")
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "old"}},
        surface_op="append",
    )
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "new"}},
        surface_op={"op": "replace", "start": 1, "end": 1},
        source_event_seqs=(1,),
    )
    expected = derive_messages(session.snapshot_events())
    assert model_visible_messages(session) == expected


def test_detached_session_falls_back_to_pure_fold() -> None:
    session = Session("mv_detached")
    session.append(SURFACE_USER_TYPE, {"content": "q"}, surface_op="append")
    assert session.derive_messages() == [{"role": "user", "content": "q"}]
