"""P2-22 / P-L4 — yaml-only spine EP registry drift guard (ADR-0195 §7).

Production spine execution points must be registered as yaml ``category`` rows
using ``SpineEventPayload``; ``SPINE_EXECUTION_POINTS`` must stay aligned with
that registry (no shadow tuple in ``manifest.py``).
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.observability.spine.manifest.manifest import EXECUTION_POINTS
from lca_kernel.events.payloads.payloads_spine import (
    SPINE_EXECUTION_POINTS,
    category_to_spine_ep,
)
from lca_kernel.events.registry.registry import EventRegistry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _REPO_ROOT / "lca_kernel" / "events" / "config"

# yaml spine categories registered without a distinct bare EP (variant rows).
_YAML_SPINE_CATEGORY_WITHOUT_EP_BASELINE: frozenset[str] = frozenset(
    {
        "spine.llm.request.header.assistant",
    }
)


def _spine_eps_from_yaml_registry() -> frozenset[str]:
    registry = EventRegistry.load(_CONFIG_DIR, catalog={})
    eps: set[str] = set()
    unmapped: list[str] = []
    for spec in registry.specs:
        cat = spec.category.value
        if not cat.startswith("spine."):
            continue
        ep = category_to_spine_ep(cat)
        if ep is None:
            unmapped.append(cat)
            continue
        eps.add(ep)
    new_unmapped = sorted(set(unmapped) - _YAML_SPINE_CATEGORY_WITHOUT_EP_BASELINE)
    assert not new_unmapped, (
        "P-L4: new yaml spine categories lack category_to_spine_ep mapping:\n"
        + "\n".join(f"  - {c}" for c in new_unmapped)
        + "\nAdd EP to spine.yaml + SPINE_EXECUTION_POINTS or extend baseline with delete-when."
    )
    return frozenset(eps)


def test_manifest_aliases_spine_execution_points() -> None:
    from lca_kernel.events.payloads.payloads_spine import SPINE_EXECUTION_POINTS

    assert tuple(EXECUTION_POINTS) == SPINE_EXECUTION_POINTS


def test_spine_execution_points_match_yaml_registry() -> None:
    """Every SPINE_EXECUTION_POINTS entry must have a yaml category row."""
    yaml_eps = _spine_eps_from_yaml_registry()
    code_eps = frozenset(SPINE_EXECUTION_POINTS)
    missing_in_yaml = sorted(code_eps - yaml_eps)
    extra_in_yaml = sorted(yaml_eps - code_eps)
    assert not missing_in_yaml, (
        "SPINE_EXECUTION_POINTS contains EPs not registered in yaml:\n"
        + "\n".join(f"  - {ep}" for ep in missing_in_yaml)
    )
    assert not extra_in_yaml, (
        "yaml registers spine EPs absent from SPINE_EXECUTION_POINTS:\n"
        + "\n".join(f"  - {ep}" for ep in extra_in_yaml)
    )


def test_spine_execution_points_closed_set_no_duplicates() -> None:
    assert len(SPINE_EXECUTION_POINTS) == len(set(SPINE_EXECUTION_POINTS))
