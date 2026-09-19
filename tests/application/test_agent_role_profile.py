"""Agent role_profile preservation test (PR-3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lca.application.api.api import Agent
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest


def test_agent_preserves_role_profile_extra() -> None:
    profile = RoleProfile(
        role="R",
        goal="G",
        backstory="B",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra={"assistant_id": "asst_1", "assistant_home_path": "/home/x"},
    )
    fake_llm = MagicMock()
    fake_spawned = MagicMock()
    with patch("lca.application.api.api.spawn_agent", return_value=fake_spawned) as spawn:
        agent = Agent(
            role="R",
            goal="G",
            backstory="B",
            tools=(),
            llm=fake_llm,
            role_profile=profile,
        )
    assert agent.role_profile.extra["assistant_id"] == "asst_1"
    assert agent.role_profile.extra["assistant_home_path"] == "/home/x"
    spawn.assert_called_once()
