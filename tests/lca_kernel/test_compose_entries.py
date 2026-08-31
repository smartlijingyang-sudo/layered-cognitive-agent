"""Tests for compose_entries — deepseek-style multi-layer patch composition.

``compose_entries`` merges bundle / profile / home / overlay patches into a
single effective entry list. Per ADR-0115 K1a + deepseek app-boot pattern,
later layers win per-id; dict config keys deep-merge; ``id`` is preserved.
"""

from __future__ import annotations

from lca_kernel.source import compose_entries


def test_compose_entries_returns_empty_when_no_layers() -> None:
    assert compose_entries() == []


def test_compose_entries_flattens_single_layer() -> None:
    bundle = [{"id": "p1", "$module": "m.p1", "config": {"k": 1}}]
    out = compose_entries(bundle_patches=bundle)
    assert out == [{"id": "p1", "$module": "m.p1", "config": {"k": 1}}]


def test_compose_entries_profile_overrides_bundle_same_id() -> None:
    bundle = [{"id": "p1", "config": {"a": 1, "b": 2}}]
    profile = [{"id": "p1", "config": {"a": 99}}]
    out = compose_entries(bundle_patches=bundle, profile_patches=profile)
    assert len(out) == 1
    assert out[0]["id"] == "p1"
    # b is preserved from bundle; a overridden by profile.
    assert out[0]["config"]["a"] == 99
    assert out[0]["config"]["b"] == 2


def test_compose_entries_home_layer_can_introduce_new_plugin() -> None:
    bundle = [{"id": "p1", "config": {"x": 1}}]
    home = [{"id": "p2", "config": {"y": 2}}]
    out = compose_entries(bundle_patches=bundle, home_patches=home)
    assert {e["id"] for e in out} == {"p1", "p2"}


def test_compose_entries_overlays_win_over_all_lower_layers() -> None:
    bundle = [{"id": "p1", "config": {"a": 1}}]
    profile = [{"id": "p1", "config": {"a": 2}}]
    home = [{"id": "p1", "config": {"a": 3}}]
    overlays = [{"id": "p1", "config": {"a": 4}}]
    out = compose_entries(
        bundle_patches=bundle,
        profile_patches=profile,
        home_patches=home,
        overlays=overlays,
    )
    assert out[0]["config"]["a"] == 4


def test_compose_entries_deep_merges_nested_config() -> None:
    bundle = [{"id": "p1", "config": {"outer": {"inner_a": 1, "inner_b": 2}}}]
    profile = [{"id": "p1", "config": {"outer": {"inner_b": 99, "inner_c": 3}}}]
    out = compose_entries(bundle_patches=bundle, profile_patches=profile)
    assert out[0]["config"]["outer"]["inner_a"] == 1  # preserved
    assert out[0]["config"]["outer"]["inner_b"] == 99  # overridden
    assert out[0]["config"]["outer"]["inner_c"] == 3  # added


def test_compose_entries_preserves_first_seen_order() -> None:
    """Same id appearing in multiple layers keeps the earliest position."""
    bundle = [{"id": "p1"}, {"id": "p2"}]
    profile = [{"id": "p1"}, {"id": "p3"}]
    out = compose_entries(bundle_patches=bundle, profile_patches=profile)
    ids = [e["id"] for e in out]
    assert ids == ["p1", "p2", "p3"]


def test_compose_entries_overlay_only_plugins_land_at_end() -> None:
    bundle = [{"id": "p1"}]
    overlays = [{"id": "pX"}, {"id": "pY"}]
    out = compose_entries(bundle_patches=bundle, overlays=overlays)
    ids = [e["id"] for e in out]
    assert ids[0] == "p1"
    assert set(ids) == {"p1", "pX", "pY"}


def test_compose_entries_skips_entries_without_id() -> None:
    bundle = [{"id": "p1"}, {"no_id_here": True}]
    out = compose_entries(bundle_patches=bundle)
    assert len(out) == 1
    assert out[0]["id"] == "p1"


def test_compose_entries_id_is_preserved_in_merge() -> None:
    """``id`` key is not deep-merged; it always reflects the entry identity."""
    bundle = [{"id": "p1", "config": {"a": 1}}]
    profile = [{"id": "p1", "config": {"a": 2}}]
    out = compose_entries(bundle_patches=bundle, profile_patches=profile)
    assert out[0]["id"] == "p1"
