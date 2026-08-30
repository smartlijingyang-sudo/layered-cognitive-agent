"""RunManifest holds journal seq, not a hard event_id (ADR-0096 §I7)."""

from lca.contracts.observability.run_manifest import RunManifest


def test_run_manifest_has_terminal_event_seq_field() -> None:
    manifest = RunManifest(run_id="r1")
    assert hasattr(manifest, "terminal_event_seq")
    assert isinstance(manifest.terminal_event_seq, int)
    assert manifest.terminal_event_seq == 0  # default


def test_run_manifest_no_longer_has_terminal_event_id() -> None:
    manifest = RunManifest(run_id="r1")
    assert not hasattr(manifest, "terminal_event_id")


def test_run_manifest_terminal_seq_roundtrip() -> None:
    manifest = RunManifest(run_id="r1", terminal_event_seq=5)
    data = manifest.to_dict()
    assert data["terminal_event_seq"] == 5
    assert "terminal_event_id" not in data
    restored = RunManifest.from_dict(data)
    assert restored.terminal_event_seq == 5


def test_run_manifest_terminal_seq_zero_means_not_finished() -> None:
    """Per ADR-0096 §I7: terminal_event_seq > 0 iff run 已 finished。"""
    manifest = RunManifest(run_id="r1")
    assert manifest.terminal_event_seq == 0  # unfinished
    manifest_finished = RunManifest(run_id="r1", terminal_event_seq=3)
    assert manifest_finished.terminal_event_seq > 0  # finished
