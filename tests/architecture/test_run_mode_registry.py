"""Run-mode registry tests — ADR-0076 §六 verification.

The ``run_mode_registry`` capability seam replaces
``gateway/modes.py:resolve_lca_mode()``'s string ``if/elif`` dispatch.
This module enforces the contract:

1. The Tier-1 seam plugin mounts an empty ``RunModeRegistry`` on the
   ctx; production profiles opt in by enabling the plugin.
2. Each Gateway mode adapter is registered by its own plugin entry (solo / team / cordis-creator), so a profile can replace one mode without coupling the others.

3. :meth:`RunModeRegistry.resolve` returns the first adapter whose
   ``matches`` predicate accepts the model id; if none match, the
   configured default is returned.
4. The mode adapter base shape (Protocol) is honored by the three
   built-in adapters so a replacement profile can disable the defaults
   and register a narrower set without touching the gateway.
"""

from __future__ import annotations

from typing import Any

import pytest

from gateway.plugins.default_modes import (
    _CordisCreatorModeAdapter,
    _SoloModeAdapter,
    _TeamModeAdapter,
)
from lca.contracts.capabilities import (
    CORDIS_CONTROL_TOOL_FACTORY,
    CORDIS_CREATOR_ROLE,
    RUN_MODE_REGISTRY,
    TEAM_CASTER,
    TEAM_ROLE_LIBRARY,
)
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.protocols.run_mode import ModeAdapter
from lca.harness.plugin_api import definition_from_plugin
from lca.plugins.seam_definitions.run_mode_registry import (
    RunModeRegistry,
)

# ── Tier-1 seam ──────────────────────────────────────────────────────


def test_seam_provides_empty_registry() -> None:
    """``lca-run-mode-registry-seam.setup`` mounts an empty registry on ctx."""

    from lca.plugins.seam_definitions.run_mode_registry import setup as seam_setup

    assert seam_setup is not None
    registry = RunModeRegistry()
    # Empty registry → resolver raises LookupError unless default is set.
    import pytest

    with pytest.raises(LookupError):
        registry.resolve("solo")
    # Empty registry has zero registered entries.
    assert registry.registered() == ()
    # Capability key matches the seam contract.
    assert RUN_MODE_REGISTRY.key == "run_mode_registry"


# ── Gateway composition adapters ─────────────────────────────────────


def test_builtin_mode_plugins_are_entry_local() -> None:
    """Each default adapter owns one plugin entry and its direct dependencies.

    A replacement profile can now disable ``lca-mode-team-default`` or add a
    different Creator adapter without editing a shared defaults registrar.
    """

    from gateway.plugins.cordis_creator_mode import setup as creator_setup
    from gateway.plugins.solo_mode import setup as solo_setup
    from gateway.plugins.team_mode import setup as team_setup

    solo = definition_from_plugin(solo_setup)
    team = definition_from_plugin(team_setup)
    creator = definition_from_plugin(creator_setup)

    assert solo.spec.id == "lca-mode-solo-default"
    assert solo.required_capability_keys == (RUN_MODE_REGISTRY.key,)
    assert team.spec.id == "lca-mode-team-default"
    assert team.required_capability_keys == (
        RUN_MODE_REGISTRY.key,
        TEAM_ROLE_LIBRARY.key,
        TEAM_CASTER.key,
    )
    assert creator.spec.id == "lca-mode-cordis-creator-default"
    assert creator.required_capability_keys == (
        RUN_MODE_REGISTRY.key,
        CORDIS_CREATOR_ROLE.key,
        CORDIS_CONTROL_TOOL_FACTORY.key,
    )


def test_defaults_register_three_modes() -> None:
    """The defaults plugin populates the registry with three adapters."""

    registry = RunModeRegistry()
    registry.register(_SoloModeAdapter())
    registry.register(_TeamModeAdapter())
    registry.register(_CordisCreatorModeAdapter())

    keys = {entry.key for entry in registry.registered()}
    assert keys == {"solo", "team", "cordis-creator"}
    roles = {entry.role for entry in registry.registered()}
    assert roles == {"助手", "cordis-creator", ""}


def test_each_default_adapter_conforms_to_mode_adapter_protocol() -> None:
    """All default adapters satisfy the contracts-level ModeAdapter protocol."""

    for adapter in (
        _SoloModeAdapter(),
        _TeamModeAdapter(),
        _CordisCreatorModeAdapter(),
    ):
        assert isinstance(adapter, ModeAdapter)


# ── Resolution semantics ─────────────────────────────────────────────


def test_resolve_matches_first_adaptor_in_registration_order() -> None:
    """First registered adapter whose ``matches`` returns True wins."""

    registry = RunModeRegistry()

    class _LaterAdapter:
        @property
        def key(self) -> str:
            return "later"

        @property
        def role(self) -> str:
            return "later-role"

        def matches(self, model: str) -> bool:
            return model == "shared"

        async def build(self, request: Any) -> Any:
            return None

    class _EarlierAdapter:
        @property
        def key(self) -> str:
            return "earlier"

        @property
        def role(self) -> str:
            return "earlier-role"

        def matches(self, model: str) -> bool:
            return model == "shared"

        async def build(self, request: Any) -> Any:
            return None

    registry.register(_LaterAdapter())  # registered first
    registry.register(_EarlierAdapter())  # registered second, but should lose

    resolved = registry.resolve("shared")
    assert resolved.key == "later"


def test_resolve_falls_back_to_default_key_when_no_adaptor_matches() -> None:
    """Unmatched model ids return the configured default adapter."""

    registry = RunModeRegistry()
    registry.register(_SoloModeAdapter())
    registry.register(_TeamModeAdapter())
    registry.register(_CordisCreatorModeAdapter())
    registry.set_default(_SoloModeAdapter().key)

    resolved = registry.resolve("totally-unknown-model")
    assert resolved.key == "solo"


def test_resolve_falls_back_to_builtin_default_when_unset() -> None:
    """``RunModeRegistry.DEFAULT_MODE_KEY`` (``"solo"``) is the implicit fallback."""

    registry = RunModeRegistry()
    registry.register(_SoloModeAdapter())

    assert registry.resolve("").key == "solo"
    assert registry.resolve("ANY-UNKNOWN").key == "solo"


def test_resolve_strips_and_lowercases_model_ids() -> None:
    """``resolve("  TEAM  ")`` matches the team adapter."""

    registry = RunModeRegistry()
    registry.register(_TeamModeAdapter())

    assert registry.resolve("  TEAM  ").key == "team"
    assert registry.resolve("Auto").key == "team"  # alias


def test_resolve_raises_when_registry_is_empty() -> None:
    """An empty registry with no default raises :class:`LookupError`."""

    registry = RunModeRegistry()
    import pytest

    with pytest.raises(LookupError):
        registry.resolve("solo")


# ── Plugin registration ──────────────────────────────────────────────


def test_duplicate_registration_is_rejected() -> None:
    """A second registration under the same key raises :class:`KeyError`."""

    registry = RunModeRegistry()
    registry.register(_SoloModeAdapter())
    import pytest

    with pytest.raises(KeyError):
        registry.register(_SoloModeAdapter())


def test_default_must_reference_a_registered_adapter() -> None:
    """``set_default`` rejects unknown keys so profiles fail closed at boot."""

    registry = RunModeRegistry()
    registry.register(_SoloModeAdapter())
    import pytest

    with pytest.raises(KeyError):
        registry.set_default("never-registered")


# ── End-to-end: gateway uses the registry ────────────────────────────


def test_gateway_resolve_lca_mode_uses_registry_when_provided() -> None:
    """``resolve_lca_mode(model, registry=...)`` consults the registry."""

    from gateway.modes import (
        CORDIS_CREATOR_MODE_KEY,
        SOLO_MODE_KEY,
        resolve_lca_mode,
    )

    registry = RunModeRegistry()
    registry.register(_SoloModeAdapter())
    registry.register(_TeamModeAdapter())
    registry.register(_CordisCreatorModeAdapter())

    assert resolve_lca_mode("solo", registry=registry) == SOLO_MODE_KEY
    assert resolve_lca_mode("team", registry=registry) == "team"
    assert resolve_lca_mode("auto", registry=registry) == "team"
    assert resolve_lca_mode("cordis-creator", registry=registry) == CORDIS_CREATOR_MODE_KEY
    # Unknown model → default fallback
    assert resolve_lca_mode("totally-unknown", registry=registry) == SOLO_MODE_KEY


def test_profile_mode_requires_a_bound_mode_registry() -> None:
    """Production profile resolution rejects a missing mode capability."""

    from gateway.modes import resolve_profile_mode

    class _MissingRegistryContext:
        def inject(self, key: str) -> object:
            raise KeyError(key)

    with pytest.raises(MissingCapabilityError):
        resolve_profile_mode(_MissingRegistryContext(), "solo")


def test_profile_mode_uses_the_bound_mode_registry() -> None:
    """Production profile resolution delegates all matching to the registry."""

    from gateway.modes import resolve_profile_mode

    registry = RunModeRegistry()
    registry.register(_SoloModeAdapter())
    registry.register(_TeamModeAdapter())
    registry.register(_CordisCreatorModeAdapter())

    class _BoundRegistryContext:
        def inject(self, key: str) -> object:
            assert key == RUN_MODE_REGISTRY.key
            return registry

    assert resolve_profile_mode(_BoundRegistryContext(), "AUTO") == "team"


def test_gateway_resolve_lca_mode_falls_back_without_registry() -> None:
    """Without a registry, the function uses the static fallback map."""

    from gateway.modes import (
        CORDIS_CREATOR_MODE_KEY,
        SOLO_MODE_KEY,
        resolve_lca_mode,
    )

    assert resolve_lca_mode("solo") == SOLO_MODE_KEY
    assert resolve_lca_mode("TEAM") == "team"
    assert resolve_lca_mode("AUTO") == "team"
    assert resolve_lca_mode("cordis-creator") == CORDIS_CREATOR_MODE_KEY
    # Unknown → solo by default
    assert resolve_lca_mode("totally-unknown") == SOLO_MODE_KEY


__all__ = [
    "test_builtin_mode_plugins_are_entry_local",
    "test_default_must_reference_a_registered_adapter",
    "test_defaults_register_three_modes",
    "test_duplicate_registration_is_rejected",
    "test_each_default_adapter_conforms_to_mode_adapter_protocol",
    "test_gateway_resolve_lca_mode_falls_back_without_registry",
    "test_gateway_resolve_lca_mode_uses_registry_when_provided",
    "test_profile_mode_requires_a_bound_mode_registry",
    "test_profile_mode_uses_the_bound_mode_registry",
    "test_resolve_falls_back_to_builtin_default_when_unset",
    "test_resolve_falls_back_to_default_key_when_no_adaptor_matches",
    "test_resolve_matches_first_adaptor_in_registration_order",
    "test_resolve_raises_when_registry_is_empty",
    "test_resolve_strips_and_lowercases_model_ids",
    "test_seam_provides_empty_registry",
]
