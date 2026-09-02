"""Architecture test — PromptSectionRegistry seam is closed and exclusive."""

from __future__ import annotations

from lca.contracts.capabilities import PROMPT_SECTION_REGISTRY
from lca.harness.profile.resolve import resolve_profile


def test_registry_plugin_provides_the_seam() -> None:
    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    registry = by_id["lca-prompt-section-registry"]
    assert PROMPT_SECTION_REGISTRY.key in registry.provided_capability_keys


def test_sections_plugin_registers_every_required_section() -> None:
    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    sections = by_id["lca-brain-prompt-sections"]
    assert sections.required_capability_keys == (PROMPT_SECTION_REGISTRY.key,)


def test_sections_plugin_declares_no_provides() -> None:
    """Sections contribute to the registry, not a capability key.

    The capability seams (PROMPT_ASSEMBLER / PROMPT_TEMPLATE_SELECTOR /
    PROMPT_TEMPLATE_PROVIDER) are owned by the assembler, selector, and
    template-provider plugins; sections only deposit instances into the
    closed registry.
    """

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    assert by_id["lca-brain-prompt-sections"].provided_capability_keys == ()
