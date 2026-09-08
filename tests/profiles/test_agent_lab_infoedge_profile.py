"""agent-lab-infoedge profile is a prototype dual-mount; web-standard stays clean."""

from __future__ import annotations

from pathlib import Path

from lca.harness.profile.resolve.resolve import resolve_profile
from lca.harness.profile.resolve.source import load_profile_source

REPO_ROOT = Path(__file__).resolve().parents[2]
INFOEDGE_PROFILE = REPO_ROOT / "profiles" / "agent-lab-infoedge.yaml"
WEB_STANDARD_PROFILE = REPO_ROOT / "profiles" / "web-standard.yaml"


def test_agent_lab_infoedge_profile_loads() -> None:
    src = load_profile_source(INFOEDGE_PROFILE)
    assert src is not None
    assert "bundles/agent-lab-infoedge.yaml" in src.bundles
    assert "bundles/declarative-phase-graph.yaml" in src.bundles
    assert "bundles/web-app.yaml" in src.bundles
    ids = {entry.get("id") for entry in src.entries}
    assert "lca-loop-infoedge" in ids
    assert "lca-run-loop-driver-registry" in ids
    registry = next(
        entry for entry in src.entries if entry.get("id") == "lca-run-loop-driver-registry"
    )
    assert registry.get("config", {}).get("default") == "infoedge"


def test_agent_lab_infoedge_profile_resolves() -> None:
    resolved = resolve_profile(INFOEDGE_PROFILE)
    ids = {plugin.id for plugin in resolved.plugins if not plugin.disabled}
    assert "lca-loop-infoedge" in ids
    assert "lca-run-loop-driver-registry" in ids
    registry = next(
        plugin for plugin in resolved.plugins if plugin.id == "lca-run-loop-driver-registry"
    )
    assert getattr(registry.config, "default", None) == "infoedge"


def test_web_standard_does_not_mount_infoedge() -> None:
    src = load_profile_source(WEB_STANDARD_PROFILE)
    assert "bundles/agent-lab-infoedge.yaml" not in src.bundles
    ids = {entry.get("id") for entry in src.entries}
    assert "lca-loop-infoedge" not in ids
    text = WEB_STANDARD_PROFILE.read_text(encoding="utf-8")
    assert "agent-lab-infoedge" not in text
    assert "lca-loop-infoedge" not in text
    assert "infoedge" not in text.lower()
