"""Structural checks for the inbox mutation/projection seam."""

from __future__ import annotations

import inspect

from lca.harness.session import inbox, inbox_projection


def test_inbox_delegates_recovery_and_payload_conversion() -> None:
    """Inbox should not duplicate journal replay or wire conversion logic."""

    source = inspect.getsource(inbox)
    assert "InboxProjector.recover" in source
    assert "InboxProjector.message_payload" in source
    assert "def _recover" not in source
    assert "def _messages_from_event" not in source
    assert "def _message_ids" not in source


def test_inbox_projector_owns_pure_replay_surface() -> None:
    """Recovery is exposed independently of a live SessionStore."""

    assert hasattr(inbox_projection.InboxProjector, "recover")
    assert hasattr(inbox_projection.InboxProjector, "message_payload")
    source = inspect.getsource(inbox_projection.InboxProjector)
    assert "SessionStore" not in source
    assert "async def" not in source
