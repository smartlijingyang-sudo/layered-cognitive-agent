"""Substitution gates for PromptReasoner template-content selection."""

from __future__ import annotations

from pathlib import Path

from lca.contracts.capabilities import (
    PROMPT_ASSEMBLER,
    PROMPT_TEMPLATE_PROVIDER,
    PROMPT_TEMPLATE_SELECTOR,
)
from lca.harness.profile.resolve import resolve_profile
from lca.plugins.prompts.template_provider import Config as ProviderConfig

REPO = Path(__file__).resolve().parents[2]


def test_builtin_provider_has_the_complete_standard_template_set() -> None:
    """The default content plugin produces every template used by PromptReasoner."""

    from lca.plugins.prompts.template_provider import _builtin_templates

    templates = _builtin_templates()
    assert set(templates) == {"react_prompt", "routing_prompt", "hierarchical_prompt"}
    assert all(t.variant for t in templates.values())


def test_provider_config_keeps_extra_fields_out() -> None:
    """A misconfigured provider fails closed at Pydantic parse time."""

    ProviderConfig(profile_templates=(), section_overrides={})


def test_standard_brain_plugins_require_the_template_provider() -> None:
    """Templates are declared profile dependencies of both standard brain factories."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    assert (
        PROMPT_TEMPLATE_PROVIDER.key
        in by_id["lca-prompt-template-provider-builtin"].provided_capability_keys
    )
    for plugin_id in ("lca-brain-simple", "lca-brain-modular"):
        definition = by_id.get(plugin_id)
        if definition is not None:
            assert PROMPT_ASSEMBLER.key in definition.required_capability_keys
            assert PROMPT_TEMPLATE_SELECTOR.key in definition.required_capability_keys


def test_brain_factory_has_no_direct_builtin_prompt_loader() -> None:
    """Only the profile-selected catalog plugin may load bundled templates."""

    source = (REPO / "lca/cognition/brain/default_factory.py").read_text(encoding="utf-8")
    assert "load_builtin_prompt" not in source
