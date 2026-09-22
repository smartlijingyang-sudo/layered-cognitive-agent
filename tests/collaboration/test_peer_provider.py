"""Tests for PeerProfileResolver and PeerAssistantMaterializer (ADR-0250)."""

import json
from pathlib import Path

import pytest

from lca.application.collaboration.peer_provider import (
    PeerProfileResolver,
    materialize_peer_assistant,
)


def test_peer_profile_resolver_resolves_guanlan(tmp_path: Path):
    resolver = PeerProfileResolver(base_home=tmp_path)
    profile = resolver.resolve("architecture/guanlan")

    assert profile.peer_id == "arch_guanlan"
    assert profile.name == "观澜"
    assert "边界" in profile.role or "契约" in profile.role
    assert profile.home_namespace == str(tmp_path / "assistants" / "arch_guanlan")
    assert "contracts" in profile.capabilities or "adr_guard" in profile.capabilities


def test_peer_profile_resolver_triad(tmp_path: Path):
    resolver = PeerProfileResolver(base_home=tmp_path)
    triad = resolver.resolve_triad()

    assert len(triad) == 3
    peer_ids = {p.peer_id for p in triad}
    assert peer_ids == {"arch_guanlan", "arch_hengyue", "arch_jingchuan"}


def test_peer_profile_resolver_unknown_role(tmp_path: Path):
    resolver = PeerProfileResolver(base_home=tmp_path)
    with pytest.raises(KeyError, match="Role not found"):
        resolver.resolve("nonexistent/role")


def test_materialize_peer_assistant_creates_files(tmp_path: Path):
    resolver = PeerProfileResolver(base_home=tmp_path)
    profile = resolver.resolve("architecture/guanlan")

    home_dir = materialize_peer_assistant(profile)
    assert home_dir.is_dir()
    assert (home_dir / "SOUL.md").is_file()
    assert (home_dir / "USER.md").is_file()
    assert (home_dir / "AGENTS.md").is_file()
    assert (home_dir / "meta.json").is_file()

    # 验证 meta.json 结构与确定性 (C8)
    meta = json.loads((home_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["peer_id"] == "arch_guanlan"
    assert meta["name"] == "观澜"

    # 验证 SOUL.md 包含角色卡精神
    soul = (home_dir / "SOUL.md").read_text(encoding="utf-8")
    assert "第一性原理" in soul or "观澜" in soul

    # 幂等性测试 (C9)
    home_dir2 = materialize_peer_assistant(profile)
    assert home_dir2 == home_dir


def test_peer_profile_resolver_resolves_generic_role(tmp_path: Path):
    resolver = PeerProfileResolver(base_home=tmp_path)
    profile = resolver.resolve("engineering/engineering-senior-developer")
    assert profile.peer_id == "engineering_engineering-senior-developer"
    assert not profile.peer_id.startswith("arch_")
    assert profile.home_namespace == str(
        tmp_path / "assistants" / "engineering_engineering-senior-developer"
    )

    # 验证 resolve_team
    team = resolver.resolve_team(
        ("engineering/engineering-senior-developer", "architecture/guanlan")
    )
    assert len(team) == 2
    assert team[0].peer_id == "engineering_engineering-senior-developer"
    assert team[1].peer_id == "arch_guanlan"
