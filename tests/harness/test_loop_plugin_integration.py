"""Test that build_live_agent resolves the loop builder from plugin scope.

This proves the agent loop is fully pluggable through YAML configuration.
"""

from pathlib import Path

import pytest

from lca.contracts.harness.plugin import ScopeKind
from lca.harness.kernel.scope import ScopedPluginHost
from lca.harness.session.inbox import Inbox
from lca.harness.session.persistence import JsonlSessionPersistence
from lca.harness.session.store import SessionStore
from lca.layer4_app.harness_bridge import build_live_agent


@pytest.fixture
def profile_scope():
    """Load the web-standard profile and wrap it in a scope."""
    import asyncio

    from lca.harness.profile.boot import boot_profile

    async def _load():
        return await boot_profile(Path("profiles/web-standard.yaml"))

    tree = asyncio.run(_load())
    return ScopedPluginHost.wrap(tree.host, ScopeKind.PROFILE, "web-standard")


@pytest.fixture
def session_store(tmp_path):
    """Create a minimal session store for testing."""
    from lca.contracts.harness.session import SESSION_FORMAT_VERSION, SessionHeader

    header = SessionHeader(
        version=SESSION_FORMAT_VERSION,
        id="test-loop-plugin",
        created_at=0,
        parent_session=None,
        origin="user",
    )
    persistence = JsonlSessionPersistence(tmp_path / "test-loop-plugin.jsonl")
    return SessionStore(header, persistence=persistence)


@pytest.fixture
def inbox(session_store):
    """Create an inbox for the session."""
    return Inbox(session_store)


def test_build_live_agent_resolves_loop_from_scope(profile_scope, session_store, inbox):
    """build_live_agent should resolve agent_loop from plugin scope."""
    # Verify the scope has agent_loop registered
    builder = profile_scope.resolve("agent_loop")
    assert callable(builder), "agent_loop should be callable"

    # Call build_live_agent with the scope
    handle = build_live_agent(
        store=session_store,
        inbox=inbox,
        identity_id="test-loop-plugin",
        options={"max_steps": 3},
        plugin_scope=profile_scope,
    )

    # Verify the agent was created successfully
    assert handle is not None
    assert handle.agent is not None
    assert handle.agent.session_id == "test-loop-plugin"


def test_build_live_agent_fallback_without_scope(session_store, inbox):
    """build_live_agent should fall back to default builder when scope is None."""
    # Call build_live_agent without a scope
    handle = build_live_agent(
        store=session_store,
        inbox=inbox,
        identity_id="test-fallback",
        options={"max_steps": 3},
        plugin_scope=None,
    )

    # Should still work using the fallback builder
    assert handle is not None
    assert handle.agent is not None


def test_loop_plugin_is_loaded_from_yaml(profile_scope):
    """Verify loop_cognitive plugin is loaded from base-spine.yaml."""
    # The agent_loop service should be available in the profile scope
    agent_loop = profile_scope.resolve("agent_loop")
    assert agent_loop is not None

    # It should be the build_cognitive_live_agent function
    from lca.plugins.loop_cognitive import build_cognitive_live_agent

    assert agent_loop is build_cognitive_live_agent
