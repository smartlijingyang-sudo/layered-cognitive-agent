"""Substitution gates for the Cordis Composer invariant-checking policy."""

from __future__ import annotations

import asyncio
from pathlib import Path

from lca.contracts.capabilities import COMPOSITION_INVARIANT_CHECKER
from lca.harness.profile.boot import boot_profile
from lca.harness.profile.resolve import resolve_profile

REPO = Path(__file__).resolve().parents[2]


def test_composer_provider_declares_profile_selected_invariant_checker() -> None:
    """Composition policy is independently replaceable from the Composer implementation."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    assert (
        COMPOSITION_INVARIANT_CHECKER.key in by_id["lca-composer-provider"].required_capability_keys
    )
    assert (
        COMPOSITION_INVARIANT_CHECKER.key
        in by_id["lca-composition-invariant-default"].provided_capability_keys
    )


def test_booted_composer_factory_receives_the_selected_invariant_checker() -> None:
    """The resolved factory closes over the exact policy capability selected by profile."""

    ctx = asyncio.run(boot_profile("profiles/web-standard.yaml"))
    factory = ctx.inject("composition.compose_factory")
    composer = factory()

    assert composer._invariant is ctx.inject(COMPOSITION_INVARIANT_CHECKER.key)


def test_production_provider_has_no_implicit_invariant_default() -> None:
    """Direct constructor fallback remains a fixture convenience, not a provider decision."""

    source = (REPO / "lca/plugins/think/composition_provider_provider.py").read_text(
        encoding="utf-8"
    )
    assert "build_composer_factory(target)" not in source
    assert "invariant_checker=invariant_checker" in source
