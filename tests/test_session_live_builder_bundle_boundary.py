"""Regression coverage for the Session Spine bundle boundary.

The live-agent bridge cannot operate without a selected ``agent_loop``. It is
therefore an L4 Session Spine concern rather than base infrastructure. A
profile may select a loop for other runtime behavior, but it must not advertise
the dependent live-agent builder unless it also selects that Session Spine.
"""

from __future__ import annotations

import pytest

from lca.harness.profile.resolve import resolve_profile


@pytest.mark.parametrize(
    "profile_path", ("profiles/coding-agent.yaml", "profiles/genai-traced.yaml")
)
def test_tooling_profiles_do_not_claim_session_live_builder(profile_path: str) -> None:
    """Profiles without the Session Spine omit its dependent live-agent bridge."""

    resolved = resolve_profile(profile_path)
    provided = {
        capability
        for plugin in resolved.plugins
        for capability in plugin.definition.provided_capability_keys
    }

    assert "agent_loop" in provided
    assert "session_live_builder" not in provided


def test_web_runtime_co_locates_session_live_builder_with_agent_loop() -> None:
    """A runnable web profile selects both sides of the Session Spine contract."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    provided = {
        capability
        for plugin in resolved.plugins
        for capability in plugin.definition.provided_capability_keys
    }

    assert {"agent_loop", "session_live_builder"} <= provided
