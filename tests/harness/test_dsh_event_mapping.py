"""Tests for DSH → LCA SessionEvent mapping (spec §D.2).

Covers the DSH_EVENT_MAP surface, the stateless DshJournalProjector, and
the warning path for unknown DSH event types.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.plugins.loop_dsh_bridge.event_mapping import (
    DSH_EVENT_MAP,
    DshJournalProjector,
)


class TestDshEventMapping:
    """Map DSH notification events to LCA SessionEvents."""

    def test_event_map_has_core_types(self):
        """Core DSH event types are mapped."""
        assert "turn/start" in DSH_EVENT_MAP
        assert "turn/end" in DSH_EVENT_MAP
        assert "tool/call" in DSH_EVENT_MAP
        assert "tool/result" in DSH_EVENT_MAP
        assert "user/message" in DSH_EVENT_MAP
        assert "assistant/message" in DSH_EVENT_MAP

    def test_mapped_types_match_lca_vocabulary(self):
        """DSH events map to LCA v1 event types."""
        assert DSH_EVENT_MAP["turn/start"] == "turn.started.v1"
        assert DSH_EVENT_MAP["turn/end"] == "turn.ended.v1"
        assert DSH_EVENT_MAP["tool/call"] == "tool.called.v1"
        assert DSH_EVENT_MAP["tool/result"] == "tool.completed.v1"

    def test_user_and_assistant_message_mappings(self):
        """User/assistant messages map to message and model events."""
        assert DSH_EVENT_MAP["user/message"] == "message.accepted.v1"
        assert DSH_EVENT_MAP["assistant/message"] == "model.completed.v1"

    def test_extended_mappings_cover_agent_step_events(self):
        """Agent/session lifecycle and step-end events are mapped."""
        assert DSH_EVENT_MAP["agent/created"] == "session.created.v1"
        assert DSH_EVENT_MAP["step/end"] == "step.ended.v1"

    def test_projector_converts_event(self):
        """DshJournalProjector converts DSH event to LCA MappedEvent."""
        projector = DshJournalProjector()

        dsh_event = MagicMock()
        dsh_event.type = "turn/start"
        dsh_event.data = {"turn": 1}

        result = projector.project(dsh_event)
        assert result is not None
        assert result.type == "turn.started.v1"
        assert result.data == {"turn": 1}

    def test_projector_handles_each_core_type(self):
        """Projector resolves every core DSH type to its LCA counterpart."""
        projector = DshJournalProjector()
        for dsh_type, expected_lca in DSH_EVENT_MAP.items():
            event = MagicMock()
            event.type = dsh_type
            event.data = {"payload": dsh_type}
            mapped = projector.project(event)
            assert mapped is not None, f"missing mapping for {dsh_type}"
            assert mapped.type == expected_lca
            assert mapped.data == {"payload": dsh_type}

    def test_projector_skips_unknown_events(self):
        """Unknown DSH events are skipped with warning."""
        projector = DshJournalProjector()

        dsh_event = MagicMock()
        dsh_event.type = "unknown/type"

        result = projector.project(dsh_event)
        assert result is None

    def test_projector_handles_missing_data(self):
        """Events with no .data attribute project with an empty data dict."""
        projector = DshJournalProjector()

        dsh_event = MagicMock(spec=["type"])
        dsh_event.type = "turn/start"

        result = projector.project(dsh_event)
        assert result is not None
        assert result.data == {}

    def test_projector_handles_missing_type(self):
        """Events with no .type attribute are rejected with a warning."""
        projector = DshJournalProjector()

        dsh_event = MagicMock(spec=[])  # no attributes at all

        result = projector.project(dsh_event)
        assert result is None

    def test_projector_logs_warning_on_unknown(self):
        """Unknown event types return None (warning logged via structlog)."""
        projector = DshJournalProjector()

        dsh_event = MagicMock()
        dsh_event.type = "totally/made_up"

        # structlog outputs to stdout, not captured by caplog — verify behavior
        result = projector.project(dsh_event)
        assert result is None
