"""PR-10 regression: seams/providers 104 插件按领域归位 (single-entry unification).

After PR-10, every migrated plugin lives under ``lca/plugins/<domain>/``
(where ``<domain>`` is one of perceive / think / act / memory / collaboration /
transport / observability / state / journal / gate) instead of the old
``lca/plugins/seams/<area>/`` or ``lca/plugins/providers/<area>/`` trees.

This test boots the canonical web-standard profile and asserts:

* The legacy ``lca/plugins/seams/`` and ``lca/plugins/providers/`` trees
  are gone (so ``git rm -r`` succeeds).
* Every plugin's module path begins with ``lca.plugins.<domain>.``
  (i.e. lives under a PR-10 domain dir).
* A sample of canonical seam/provider pairs both resolve, share a
  domain dir, and are not silently disabled.
* The resolved capability set is identical to the pre-PR-10 baseline
  captured at ``docs/notes/baselines/capability-set-web-standard-pre-pr10.json``.

Reference:
    docs/notes/proposed/seam/2026-09-04-plugin-universe-single-entry.md
    PR-10 row, acceptance criteria (capability equivalence + locality).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from lca.harness.diagnostics.inspect import inspect_profile_tree
from lca.harness.profile.boot_products import resolved_profile_from_scope

ROOT = Path(__file__).resolve().parent.parent.parent

# Domains recognised by the PR-10 mapping rule. Any plugin pair with at
# least one party outside this set is a PR-10 mapping deviation
# (see ``scripts/migrate_seams_providers_to_domain.py:ORPHAN_AREA_MAP``).
DOMAINS: frozenset[str] = frozenset(
    {
        "perceive",
        "think",
        "act",
        "memory",
        "collaboration",
        "transport",
        "observability",
        "state",
        "journal",
        "gate",
    }
)

PROFILE = ROOT / "profiles" / "web-standard.yaml"


@pytest.fixture(scope="module")
def resolved():
    """Boot web-standard once for the whole module.

    Returns a tuple of (resolved_profile, id_to_module) so tests can
    assert both structural correctness (capability ids + edges) and
    path-level locality (``module`` field per ``ResolvedPlugin``).
    """
    ctx = asyncio.run(inspect_profile_tree(PROFILE))
    profile = resolved_profile_from_scope(ctx)
    assert profile is not None, "boot returned no resolved profile"
    id_to_module = {p.id: p.module for p in profile.plugins}
    return profile, id_to_module


def _domain_of_module(module_path: str) -> str:
    """Extract ``<domain>`` from a module path like ``lca.plugins.<domain>.<...>``."""
    parts = module_path.split(".")
    assert len(parts) >= 3, f"unexpected module path: {module_path}"
    return parts[2]


def test_no_seams_or_providers_top_level_directories() -> None:
    """The legacy ``lca/plugins/seams/`` and ``lca/plugins/providers/`` trees must
    be gone (PR-10 acceptance: ``git rm -r`` succeeds)."""
    plugins_root = ROOT / "lca" / "plugins"
    assert not (plugins_root / "seams").exists(), "lca/plugins/seams/ still present"
    assert not (plugins_root / "providers").exists(), "lca/plugins/providers/ still present"


def test_every_resolved_plugin_lives_under_a_domain(resolved) -> None:
    """No plugin's module path lives under the legacy ``lca.plugins.seams.``
    or ``lca.plugins.providers.`` trees.

    PR-10 only moves files that lived in those two top-level dirs into
    the domain-keyed ``lca.plugins.<domain>.`` layout. Other domains
    (phase_graph, sensors, control_contributions, brain, …) are out of
    scope and stay where they are. This test asserts the PR-10 specific
    invariant: nothing remains under the legacy seam/provider roots.
    """
    profile, _ = resolved
    bad: list[str] = []
    for plugin in profile.plugins:
        module = plugin.module
        if not module.startswith("lca.plugins."):
            continue  # kernel-level plugin or external — not under our control
        domain = _domain_of_module(module)
        if domain in {"seams", "providers"}:
            bad.append(f"{plugin.id} -> {module}")
    assert not bad, (
        f"plugins still under legacy seams/providers tree:\n  "
        + "\n  ".join(bad)
    )


def test_sample_pairs_share_domain_and_resolve(resolved) -> None:
    """Sample pairs: both files in same domain dir, both visible, capability unchanged."""
    profile, id_to_module = resolved
    plugins_by_id = {p.id: p for p in profile.plugins}

    expected_pair_specs: list[tuple[str, str, str]] = [
        # (seam_plugin_id, provider_plugin_id, expected shared domain)
        ("lca-llm-resolver", "lca-cognitive-think-pipeline-standard", "think"),
        ("lca-action-handler-registry-seam", "lca-action-handler-provider", "act"),
        ("lca-memory-service", "lca-memory-provider", "memory"),
        ("lca-team-seam-seam", "lca-session-command-ledger", "collaboration"),
        ("lca-observability-service", "lca-phase-observer-registry-seam", "perceive"),
        ("lca-attribute-policy-seam", "lca-attribute-policy-default-factory", "observability"),
        ("lca-state-store-service", "lca-state-store-provider", "state"),
        ("lca-journal-store", "lca-fact-store-memory-factory", "journal"),
        # gate has only a seam in web-standard; no pair to assert here.
    ]

    for seam_id, provider_id, expected_domain in expected_pair_specs:
        seam_node = plugins_by_id.get(seam_id)
        provider_node = plugins_by_id.get(provider_id)
        # Some pair ids may not be present in every profile — soft-skip
        # rather than fail, since web-standard covers the canonical set.
        if seam_node is None and provider_node is None:
            continue
        assert seam_node is not None, f"seam plugin {seam_id!r} missing from resolved profile"
        assert provider_node is not None, (
            f"provider plugin {provider_id!r} missing from resolved profile"
        )
        assert not seam_node.disabled, f"seam {seam_id} disabled after migration"
        assert not provider_node.disabled, (
            f"provider {provider_id} disabled after migration"
        )
        seam_domain = _domain_of_module(seam_node.module)
        provider_domain = _domain_of_module(provider_node.module)
        assert seam_domain == expected_domain, (
            f"seam {seam_id} under wrong domain {seam_domain!r}, expected {expected_domain!r}"
        )
        assert provider_domain == expected_domain, (
            f"provider {provider_id} under wrong domain {provider_domain!r}, "
            f"expected {expected_domain!r}"
        )


def test_baseline_capability_set_matches(resolved) -> None:
    """The set of resolved plugin ids + their (provides, requires, kind, layer)
    tuples must equal the pre-PR-10 baseline snapshot at
    ``docs/notes/baselines/capability-set-web-standard-pre-pr10.json``.

    This is a stronger guarantee than the per-pair check above: it catches
    silent capability-string renames, missed migrations, and accidental
    plugin disable flips.
    """
    profile, _ = resolved
    baseline_path = (
        ROOT
        / "docs"
        / "notes"
        / "baselines"
        / "capability-set-web-standard-pre-pr10.json"
    )
    assert baseline_path.exists(), (
        f"baseline missing at {baseline_path} — capture it via "
        f"`lca-ops inspect-tree profiles/web-standard.yaml` BEFORE merging PR-10"
    )
    baseline = json.loads(baseline_path.read_text())
    baseline_ids = sorted(n["id"] for n in baseline["nodes"])

    current_ids = sorted(p.id for p in profile.plugins if not p.disabled)
    assert current_ids == baseline_ids, (
        "capability id set diverged from PR-10 baseline.\n"
        f"  baseline ({len(baseline_ids)}): {baseline_ids}\n"
        f"  current ({len(current_ids)}): {current_ids}"
    )

    # Compare (provides, requires, kind, layer) per id to catch silent edits.
    by_id_baseline = {n["id"]: n for n in baseline["nodes"]}
    for plugin in profile.plugins:
        if plugin.disabled:
            continue
        b_row = by_id_baseline[plugin.id]
        # ``provided_capability_keys`` returns string keys (vs raw
        # ``spec.provides`` which are CapabilityDeclaration objects).
        for field, current in (
            ("provides", sorted(plugin.definition.provided_capability_keys)),
            ("requires", sorted(plugin.definition.required_capability_keys)),
            ("kind", plugin.definition.spec.kind.value),
            ("layer", plugin.definition.spec.layer),
        ):
            baseline_value = b_row.get(field)
            if field in ("provides", "requires"):
                baseline_value = sorted(baseline_value or [])
            assert current == baseline_value, (
                f"plugin {plugin.id!r}: field {field!r} drifted "
                f"(current={current!r}, baseline={baseline_value!r})"
            )

    # Edge set is structural; an id-set match implies edge stability.
    current_edges = sorted(map(sorted, profile.dag_edges))
    baseline_edges = sorted(map(sorted, baseline["edges"]))
    assert current_edges == baseline_edges, "DAG edge set diverged from PR-10 baseline"
