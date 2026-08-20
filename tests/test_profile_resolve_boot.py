"""ADR-0061 — resolve_profile / boot_resolved_profile contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lca.harness.profile.boot import boot_profile, boot_resolved_profile
from lca.harness.profile.resolve import ProfileResolveError, dump_resolved, resolve_profile

DEFAULT = Path("profiles/web-standard.yaml")


def test_resolve_default_profile_is_stable() -> None:
    a = resolve_profile(DEFAULT)
    b = resolve_profile(DEFAULT)
    assert a.manifest_hash == b.manifest_hash
    assert len(a.plugins) >= 40
    assert any(e[0] == "perceive" and e[1] == "sensor.clock" for e in a.dag_edges)


def test_resolve_orders_perceive_before_sensors() -> None:
    resolved = resolve_profile(DEFAULT)
    ids = [p.id for p in resolved.plugins if not p.disabled]
    assert ids.index("perceive") < ids.index("sensor.clock")
    assert ids.index("gates") < ids.index("gate.repeat-tool-call")
    assert ids.index("lca-reasoner-prompt") < ids.index("lca-brain-simple")


def test_dump_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-secret-value-should-not-leak")
    resolved = resolve_profile(DEFAULT)
    dumped = dump_resolved(resolved, redact=True)
    blob = str(dumped)
    assert "sk-secret-value-should-not-leak" not in blob
    resolver = next(p for p in dumped["plugins"] if p["id"] == "lca-llm-resolver")
    assert resolver["config"].get("api_key") in {None, "***"}


def test_disable_memory_fails_at_resolve(tmp_path: Path) -> None:
    profile = tmp_path / "no-memory.yaml"
    profile.write_text(
        "bundles:\n"
        "  - bundles/base.yaml\n"
        "  - bundles/web-app.yaml\n"
        "patch:\n"
        "  - id: lca-memory-service\n"
        "    disabled: true\n"
    )
    with pytest.raises(ProfileResolveError, match="memory"):
        resolve_profile(profile)


def test_unknown_config_field_fails(tmp_path: Path) -> None:
    profile = tmp_path / "bad-config.yaml"
    profile.write_text(
        "bundles:\n"
        "  - bundles/base.yaml\n"
        "  - bundles/web-app.yaml\n"
        "patch:\n"
        "  - id: gate.repeat-tool-call\n"
        "    config:\n"
        "      not_a_real_field: 1\n"
    )
    with pytest.raises(ProfileResolveError, match=r"gate\.repeat-tool-call"):
        resolve_profile(profile)


def test_boot_default_profile() -> None:
    ctx = asyncio.run(boot_profile(DEFAULT))
    perceive = ctx.inject("perceive")
    assert [e.id for e in perceive.members()][:2] == ["clock", "workspace-artifacts"]
    gates = ctx.inject("gates")
    assert "repeat-tool-call" in gates._entries
    assert ctx.inject("brain_factory") is not None


def test_boot_resolved_matches_facade() -> None:
    resolved = resolve_profile(DEFAULT)
    ctx = asyncio.run(boot_resolved_profile(resolved))
    assert ctx.__dict__.get("resolved_profile") is resolved
