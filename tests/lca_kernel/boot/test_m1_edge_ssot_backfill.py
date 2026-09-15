"""M1 anti-backfill: dual edge SSOT must stay retired (Issue #14)."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
PROFILES = REPO / "profiles"
BANNED_BUNDLES = frozenset(
    {
        "bundles/declarative-recovery.yaml",
        "bundles/declarative-phase-graph.yaml",
        "declarative-recovery.yaml",
        "declarative-phase-graph.yaml",
    }
)
RECOVERY_PLUGIN = REPO / "lca" / "plugins" / "loop" / "graph" / "recovery" / "plugin.py"


def _profile_bundle_entries(path: Path) -> list[str]:
    """Return only YAML ``bundles:`` list items (comments never count)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    bundles = data.get("bundles") or []
    if not isinstance(bundles, list):
        return []
    out: list[str] = []
    for item in bundles:
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, dict):
            for v in item.values():
                if isinstance(v, str):
                    out.append(v.strip())
    return out


def test_production_profiles_bundles_exclude_declarative_edge_ssot() -> None:
    """profiles/*.yaml ``bundles:`` must not re-list dual edge SSOT packs."""
    offenders: list[str] = []
    for path in sorted(PROFILES.glob("*.yaml")):
        for entry in _profile_bundle_entries(path):
            norm = entry.lstrip("./")
            if norm in BANNED_BUNDLES or any(norm.endswith(b) for b in BANNED_BUNDLES):
                offenders.append(f"{path.name}: bundles entry {entry!r}")
    assert not offenders, (
        "M1: production profiles must not load declarative-* as edge SSOT:\n"
        + "\n".join(offenders)
    )


def test_recovery_plugin_setup_is_noop_no_phase_edge_provide() -> None:
    """setup must not provide phase.edge.recovery (second edge capability)."""
    source = RECOVERY_PLUGIN.read_text(encoding="utf-8")
    assert 'provide("phase.edge.recovery"' not in source
    assert "provide('phase.edge.recovery'" not in source
    assert "provides=()" in source
    assert "M1 no-op" in source
    assert "delete-when: 2026-10-15" in source

    from lca.plugins.loop.graph.recovery import plugin as recovery_plugin

    assert recovery_plugin.SPEC.provides == ()


def test_no_profile_activates_recovery_edge_plugin_entry() -> None:
    """No profile/bundle entry may activate phase.edge.reflect_to_think.recovery."""
    needle = "phase.edge.reflect_to_think.recovery"
    module_needle = "lca.plugins.loop.graph.recovery.plugin"
    offenders: list[str] = []
    scan_roots = [REPO / "bundles", PROFILES]
    for root in scan_roots:
        paths = root.rglob("*.yaml") if root.name == "bundles" else root.glob("*.yaml")
        for path in sorted(paths):
            text = path.read_text(encoding="utf-8")
            active = "\n".join(
                ln
                for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            )
            if needle in active or module_needle in active:
                offenders.append(path.relative_to(REPO).as_posix())
    assert not offenders, (
        "M1: no profile/bundle may activate recovery edge plugin entry:\n"
        + "\n".join(offenders)
    )
