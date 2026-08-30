"""Substitution gates for PromptReasoner template-content selection."""

from __future__ import annotations

from pathlib import Path

from lca.contracts.capabilities import REASONER_TEMPLATE_CATALOG
from lca.harness.profile.resolve import resolve_profile
from lca.plugins.seam_definitions.reasoner_template_catalog import (
    BuiltinReasonerTemplateCatalog,
    Config,
)

REPO = Path(__file__).resolve().parents[2]


def test_builtin_catalog_has_the_complete_standard_template_set() -> None:
    """The default content plugin produces every template used by PromptReasoner."""

    templates = BuiltinReasonerTemplateCatalog(
        ("react_prompt", "hierarchical_prompt", "routing_prompt")
    ).templates()

    assert set(templates) == {"react_prompt", "hierarchical_prompt", "routing_prompt"}
    assert all(template.strip() for template in templates.values())


def test_catalog_config_fails_closed_when_a_required_template_is_missing() -> None:
    """A partial built-in catalog cannot silently produce an incomplete brain factory."""

    try:
        Config(template_names=("react_prompt",))
    except ValueError as exc:
        assert "missing required templates" in str(exc)
    else:  # pragma: no cover - explicit fail-closed assertion
        raise AssertionError("partial reasoner template catalog must be rejected")


def test_standard_brain_plugins_require_the_template_catalog() -> None:
    """Templates are declared profile dependencies of both standard brain factories."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    assert (
        REASONER_TEMPLATE_CATALOG.key
        in by_id["lca-reasoner-template-catalog-builtin"].provided_capability_keys
    )
    for plugin_id in ("lca-brain-simple", "lca-brain-modular"):
        definition = by_id.get(plugin_id)
        if definition is not None:
            assert REASONER_TEMPLATE_CATALOG.key in definition.required_capability_keys


def test_brain_factory_has_no_direct_builtin_prompt_loader() -> None:
    """Only the profile-selected catalog plugin may load bundled templates."""

    source = (REPO / "lca/layer1_cognitive/brain/default_factory.py").read_text(encoding="utf-8")
    assert "load_builtin_prompt" not in source
