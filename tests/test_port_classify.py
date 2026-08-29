"""Tests for scripts/port_classify.py."""

from __future__ import annotations

from scripts.port_classify import CLUSTER_MAP, classify_commit


def test_classify_locked_path() -> None:
    c = classify_commit(
        "0" * 40,
        "fix(lobehub-patches): preserve streaming output",
        ["deploy/lobehub/patches/runtime/LcaRunDriver.ts"],
    )
    assert c.cluster == "locked"
    assert c.lane == "C"


def test_classify_adr_path() -> None:
    c = classify_commit(
        "1" * 40,
        "docs(adr-0101): Tool events evidence flow",
        ["docs/adr/0101-tool-events.md"],
    )
    assert c.cluster == "C7"
    assert c.lane == "A"


def test_classify_harness_path() -> None:
    c = classify_commit(
        "2" * 40,
        "feat(harness): boot_resolved_profile()",
        ["lca/harness/profile/boot.py"],
    )
    assert c.cluster == "C9"
    assert c.lane == "A"


def test_classify_layer1_brain() -> None:
    c = classify_commit(
        "3" * 40,
        "feat(brain): improve Reasoner heuristic",
        ["lca/layer1_cognitive/brain/reasoner.py"],
    )
    assert c.cluster == "C22"
    assert c.lane == "B"


def test_classify_gateway_api_soft_lock() -> None:
    c = classify_commit(
        "4" * 40,
        "feat(gateway): add /runs/stream endpoint",
        ["gateway/runs/api.py"],
    )
    assert c.cluster == "C36"
    assert c.lane == "C"


def test_classify_chore_skipped() -> None:
    c = classify_commit(
        "5" * 40,
        "chore: format foo.py",
        ["lca/foo.py"],
    )
    assert c.cluster == "skip-chore"
    assert c.lane == "C"


def test_classify_yagni_cleanup() -> None:
    c = classify_commit(
        "6" * 40,
        "refactor: kill ObservabilityHub alias",
        ["lca/observability.py"],
    )
    assert c.cluster == "skip-yagni"
    assert c.lane == "C"


def test_classify_tests_default() -> None:
    c = classify_commit(
        "7" * 40,
        "test: cover new evidence path",
        ["tests/test_evidence.py"],
    )
    assert c.cluster == "C45"
    assert c.lane == "B"


def test_classify_keyword_fallback() -> None:
    c = classify_commit(
        "8" * 40,
        "feat: ADR follow-up notes",
        ["random_file.md"],
    )
    assert c.cluster == "C7"
    assert c.lane == "A"


def test_cluster_map_has_47_entries() -> None:
    assert len(CLUSTER_MAP) >= 47, f"CLUSTER_MAP has only {len(CLUSTER_MAP)} entries"


def test_cluster_map_covers_43_path_clusters() -> None:
    """CLUSTER_MAP must cover all path-based clusters (C1..C43).

    C44..C47 are test-bucket clusters in the spec; the classifier
    collapses all `tests/` paths into C45 (B-lane) for simplicity, so
    the path map need only declare C1..C43.
    """
    skip_ids = {"locked", "skip-chore", "skip-dsh", "skip-yagni", "unclassified"}
    ids = {c for _, c, _ in CLUSTER_MAP if c not in skip_ids}
    expected = {f"C{i}" for i in range(1, 44)}
    assert expected.issubset(ids), f"missing: {sorted(expected - ids)}"
    # Test cluster ids are emitted at runtime, not in the path map
    assert len(ids) >= 43
