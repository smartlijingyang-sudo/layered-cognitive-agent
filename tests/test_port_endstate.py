"""Tests for scripts/port_endstate.py."""

from __future__ import annotations

from scripts.port_endstate import CLUSTER_PATHS, render_card, render_one


def test_render_card_includes_all_fields() -> None:
    info = CLUSTER_PATHS["C16"]
    card = render_card(
        cluster_id="C16",
        paths=info["paths"],  # type: ignore[arg-type]
        lane=info["lane"],  # type: ignore[arg-type]
        commit_count=12,
        main_tip_sha="0dc34a1e",
        main_tip_subject="feat(tools): flatten tool observation payload",
        branch_sha="5204fd56",
        branch_subject="fix(gateway): restore LobeHub SSE",
        key_symbols=["lca/layer0_infra/tools/render_contract.py"],
    )
    assert "### C16" in card
    assert "**Lane**: B" in card
    assert "Main commits touching this cluster**: 12" in card
    assert "**Mark**: [ ] port" in card
    # C16 is Layer 0 tools — fully unlocked, not soft-lock
    assert "**Lock impact**: none" in card


def test_soft_lock_card_mentions_wire_shape() -> None:
    info = CLUSTER_PATHS["C36"]
    card = render_card(
        cluster_id="C36",
        paths=info["paths"],  # type: ignore[arg-type]
        lane=info["lane"],  # type: ignore[arg-type]
        commit_count=4,
        main_tip_sha="0dc34a1e",
        main_tip_subject="x",
        branch_sha="5204fd56",
        branch_subject="y",
        key_symbols=[],
    )
    assert "soft:gateway/runs/api.py" in card
    assert "Lane**: C" in card


def test_a_lane_card_has_no_lock_impact() -> None:
    info = CLUSTER_PATHS["C9"]
    card = render_card(
        cluster_id="C9",
        paths=info["paths"],  # type: ignore[arg-type]
        lane=info["lane"],  # type: ignore[arg-type]
        commit_count=1,
        main_tip_sha="0dc34a1e",
        main_tip_subject="x",
        branch_sha="5204fd56",
        branch_subject="y",
        key_symbols=[],
    )
    assert "**Lock impact**: none" in card
    assert "Lane**: A" in card


def test_render_one_calls_real_git() -> None:
    """Smoke: render_one against HEAD should produce non-empty content."""
    card = render_one("C16", "bae32d8c27ee2b59312303fbfa68d4738c2f316f", "origin/main")
    assert "### C16" in card
    assert "Main commits touching this cluster" in card


def test_cluster_paths_cover_47_distinct_clusters() -> None:
    expected = {f"C{i}" for i in range(1, 48)}
    assert expected.issubset(CLUSTER_PATHS.keys()), (
        f"missing: {sorted(expected - CLUSTER_PATHS.keys())}"
    )


def test_soft_lock_clusters_listed() -> None:
    """C36..C40 must all be lane C (gateway soft-lock)."""
    for cid in ("C36", "C37", "C38", "C39", "C40"):
        assert CLUSTER_PATHS[cid]["lane"] == "C", f"{cid} should be lane C"


def test_a_lane_clusters_include_contracts() -> None:
    for cid in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C9"):
        assert CLUSTER_PATHS[cid]["lane"] == "A", f"{cid} should be lane A"
