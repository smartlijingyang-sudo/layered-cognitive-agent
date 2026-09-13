"""Architecture test — role_profile stays a Cordis capability; compose does not assemble it.

eng/retire-v1-reasoner-sandbox: ``phase.think.reasoner.compose`` constructs
PromptReasoner from llm + template ports only. ``RoleProfile`` is provided by
``phase.think.role_profile`` and consumed as ``RoleSnapshot`` on the graph
boundary (``concept.role.snapshot`` / think.reason.render), not owned by
PromptReasoner.
"""

from __future__ import annotations

import pytest

from lca.contracts.capabilities import REASONER_ROLE_PROFILE
from lca.harness.profile.resolve.resolve import resolve_profile

REASONER_PLUGIN_ID = "phase.think.reasoner.compose"
ROLE_PROFILE_PROVIDER_ID = "phase.think.role_profile"


@pytest.fixture(scope="module")
def resolved() -> object:
    return resolve_profile("profiles/web-standard.yaml")


def _by_id(resolved: object) -> dict[str, object]:
    return {plugin.id: plugin.definition for plugin in resolved.plugins}


def test_role_profile_provider_exists_and_provides(resolved: object) -> None:
    definition = _by_id(resolved)[ROLE_PROFILE_PROVIDER_ID]
    assert REASONER_ROLE_PROFILE.key in definition.provided_capability_keys


def test_reasoner_compose_does_not_require_role_profile(resolved: object) -> None:
    """Compose must not assemble RoleProfile into PromptReasoner."""
    definition = _by_id(resolved)[REASONER_PLUGIN_ID]
    assert REASONER_ROLE_PROFILE.key not in definition.required_capability_keys


def test_reasoner_compose_does_not_require_tools(resolved: object) -> None:
    definition = _by_id(resolved)[REASONER_PLUGIN_ID]
    assert "tools" not in definition.required_capability_keys


def test_reasoner_compose_does_not_provide_role_profile(resolved: object) -> None:
    definition = _by_id(resolved)[REASONER_PLUGIN_ID]
    assert REASONER_ROLE_PROFILE.key not in definition.provided_capability_keys
