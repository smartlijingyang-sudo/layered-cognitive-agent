from __future__ import annotations

import pytest

from lca.contracts.harness.tasks.session import SESSION_FORMAT_VERSION, SessionHeader


def _header(**overrides: object) -> SessionHeader:
    values: dict[str, object] = {
        "version": SESSION_FORMAT_VERSION,
        "id": "session-1",
        "created_at": 100,
    }
    values.update(overrides)
    return SessionHeader(**values)


def test_session_header_accepts_traceable_creation_metadata() -> None:
    header = _header(
        parent_session="parent-1",
        origin="subagent",
        delegation_depth=2,
        agent_preset="researcher",
        profile_digest="sha256:abc",
    )

    assert header.parent_session == "parent-1"
    assert header.delegation_depth == 2


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"version": SESSION_FORMAT_VERSION + 1}, "version"),
        ({"id": ""}, "id"),
        ({"created_at": -1}, "created_at"),
        ({"delegation_depth": -1}, "delegation_depth"),
    ],
)
def test_session_header_rejects_invalid_creation_metadata(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _header(**overrides)
