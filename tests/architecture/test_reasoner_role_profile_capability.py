"""Architecture test — ``phase.think.reasoner`` consumes ``reasoner.role_profile``.

The inner think subgraph reuses a single ``PromptReasoner`` instance across
``plan`` / ``render`` / ``complete`` reason nodes, so the role identity
(role / goal / backstory / tool permission manifest) must be resolved once
at boot and provided as a typed capability — never hard-coded inside the
reasoner provider.
"""

from __future__ import annotations

import pytest

from lca.contracts.capabilities import REASONER_ROLE_PROFILE
from lca.harness.profile.resolve.resolve import resolve_profile

REASONER_PLUGIN_ID = "phase.think.reasoner"
ROLE_PROFILE_PROVIDER_ID = "phase.think.role_profile"


@pytest.fixture(scope="module")
def resolved() -> object:
    return resolve_profile("profiles/web-standard.yaml")


def _by_id(resolved: object) -> dict[str, object]:
    return {plugin.id: plugin.definition for plugin in resolved.plugins}


def test_reasoner_plugin_requires_role_profile(resolved: object) -> None:
    """``phase.think.reasoner`` must declare ``reasoner.role_profile`` in ``requires``."""

    definition = _by_id(resolved)[REASONER_PLUGIN_ID]
    assert REASONER_ROLE_PROFILE.key in definition.required_capability_keys


def test_role_profile_provider_exists_and_provides(resolved: object) -> None:
    """A dedicated provider in the bundle exposes ``reasoner.role_profile``."""

    definition = _by_id(resolved)[ROLE_PROFILE_PROVIDER_ID]
    assert REASONER_ROLE_PROFILE.key in definition.provided_capability_keys


def test_reasoner_plugin_does_not_hardcode_role_profile(resolved: object) -> None:
    """The reasoner provider must not provide the role itself.

    Two providers both providing the same ``cardinality="one"`` capability
    would force Cordis to disambiguate at boot — that is the failure mode
    this test exists to prevent once ``phase.think.role_profile`` lands.
    """

    definition = _by_id(resolved)[REASONER_PLUGIN_ID]
    assert REASONER_ROLE_PROFILE.key not in definition.provided_capability_keys
