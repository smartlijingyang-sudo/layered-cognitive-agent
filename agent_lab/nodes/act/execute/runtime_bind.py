"""Process boot for act: one Session + publish bind (FactGateway SSOT).

Called from runner / run.py. Reuses session_log._sink — no parallel Session.
"""

from __future__ import annotations

from typing import Any

_PLAN_REF = "agent_lab_act"
_PUBLISH_TOKEN: Any = None


def plan_ref() -> str:
    return _PLAN_REF


def ensure_act_runtime() -> Any:
    """Idempotent: session_log Session + FactGateway publish session."""
    global _PUBLISH_TOKEN

    from agent_lab.adapters.lca_memory import register_fixture_session
    from agent_lab.nodes.session_log._sink import configure_session, get_session
    from lca.plugins.events.publishers._session_publish import (
        current_publish_session,
        set_publish_session,
    )

    sess = get_session()
    configure_session(sess)

    if current_publish_session() is None:
        _PUBLISH_TOKEN = set_publish_session(sess)

    # Remember phase resolves the same Session (not _NoopSession).
    register_fixture_session("agent_lab_default", sess)
    return sess


def reset_act_runtime_for_tests() -> None:
    """Test helper: clear publish bind."""
    global _PUBLISH_TOKEN
    from lca.plugins.events.publishers._session_publish import reset_publish_session

    if _PUBLISH_TOKEN is not None:
        reset_publish_session(_PUBLISH_TOKEN)
        _PUBLISH_TOKEN = None
