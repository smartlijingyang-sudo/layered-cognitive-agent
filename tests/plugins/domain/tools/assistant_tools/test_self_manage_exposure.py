"""PR-2 self-management tool exposure tests.

Verifies that the assistant tool factory materializes the full
self-management family when a run binds an assistant_id, and nothing when
the run is unbound (ADR-0242 D6 + ADR-0243 D6).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.infrastructure.tools.assistant.create_skill_tool import (
    assistant_create_skill_tool_from_run,
)
from lca.infrastructure.tools.assistant.self_manage_tools import (
    _CREATE_ASSISTANT_TOOL_TOOL,
    _DELETE_ASSISTANT_SKILL_TOOL,
    _DELETE_ASSISTANT_TOOL_TOOL,
    _EDIT_ASSISTANT_SKILL_TOOL,
    _LIST_ASSISTANT_SKILLS_TOOL,
    _LIST_ASSISTANT_TOOLS_TOOL,
    _UPDATE_ASSISTANT_GRANTS_TOOL,
    _UPDATE_ASSISTANT_PROFILE_TOOL,
    _UPDATE_ASSISTANT_SOUL_TOOL,
    _UPDATE_ASSISTANT_TOOL_TOOL,
    _UPDATE_ASSISTANT_USER_TOOL,
    assistant_self_manage_tools_from_run,
)

_FULL_FAMILY = {
    _CREATE_ASSISTANT_TOOL_TOOL,
    _DELETE_ASSISTANT_SKILL_TOOL,
    _DELETE_ASSISTANT_TOOL_TOOL,
    _EDIT_ASSISTANT_SKILL_TOOL,
    _LIST_ASSISTANT_SKILLS_TOOL,
    _LIST_ASSISTANT_TOOLS_TOOL,
    _UPDATE_ASSISTANT_GRANTS_TOOL,
    _UPDATE_ASSISTANT_PROFILE_TOOL,
    _UPDATE_ASSISTANT_SOUL_TOOL,
    _UPDATE_ASSISTANT_TOOL_TOOL,
    _UPDATE_ASSISTANT_USER_TOOL,
}


def _catalog() -> MagicMock:
    return MagicMock()


def test_bound_run_has_full_family() -> None:
    tools = assistant_self_manage_tools_from_run(
        {"assistant_id": "asst_test"},
        catalog=_catalog(),
    )
    names = {tool.name for tool in tools}
    assert names == _FULL_FAMILY


def test_unbound_run_has_no_self_manage_tools() -> None:
    tools = assistant_self_manage_tools_from_run({}, catalog=_catalog())
    assert tools == []


def test_bound_run_materializes_create_skill() -> None:
    tool = assistant_create_skill_tool_from_run(
        {"assistant_id": "asst_test"},
        overlay=MagicMock(),
    )
    assert tool is not None
    assert tool.name == "create_assistant_skill"


def test_unbound_run_omits_create_skill() -> None:
    tool = assistant_create_skill_tool_from_run({}, overlay=MagicMock())
    assert tool is None
