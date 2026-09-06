"""Tests for the manifest-driven reconcile engine.

These tests cover the four reconciliation quadrants and the cold-start
orphan sweep that fixes the failure mode exposed by reverting
``inspector_shiny_text_legibility`` while lobehub-ui still held its writes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deploy.lobehub.engine import (
    Manifest,
    PatchContext,
    PatchEntry,
    PatchMeta,
    PatchModule,
    _compute_patch_hash,
    _read_manifest,
    _write_manifest,
    reconcile,
)

# ── Fixtures ───────────────────────────────────────────────────────────


def _meta(name: str, files: tuple[str, ...] = ()) -> PatchMeta:
    return PatchMeta(
        name=name,
        description=f"test patch {name}",
        files=files,
        risk="low",
        category="test",
    )


def _patch(name: str, body: str, files: tuple[str, ...] = ()) -> PatchModule:
    """A patch whose apply() writes ``body`` into the first file in ``files``.
    If ``files`` is empty, apply() does nothing — used for orphan tests."""

    def apply(ctx: PatchContext) -> bool:
        if not files:
            return False
        return ctx.write_if_changed(files[0], body)

    return PatchModule(meta=_meta(name, files), apply=apply)


def _seed_ui(ui: Path, files: dict[str, str]) -> None:
    """Pre-populate lobehub-ui with the given rel → content map."""
    ui.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = ui / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _seed_upstream(upstream: Path, files: dict[str, str]) -> None:
    upstream.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = upstream / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Point ROOT/UI/_UPSTREAM at a tmp sandbox."""
    from deploy.lobehub import engine as eng

    sandbox_root = tmp_path / "repo"
    ui = sandbox_root / "lobehub-ui"
    upstream = sandbox_root / ".lobehub-upstream"
    monkeypatch.setattr(eng, "ROOT", sandbox_root)
    monkeypatch.setattr(eng, "UI", ui)
    monkeypatch.setattr(eng, "MANIFEST_FILE", ui / ".lca-manifest.json")
    monkeypatch.setattr(eng, "LEGACY_STAMP", ui / ".lca-patched")
    monkeypatch.setattr(eng, "LEGACY_HASHES", ui / ".lca-patch-hashes")
    monkeypatch.setattr(eng, "_UPSTREAM", upstream)
    return {"root": sandbox_root, "ui": ui, "upstream": upstream}


# ── Quadrant 1: orphan → restore ───────────────────────────────────────


def test_orphan_patch_restores_written_files(sandbox: dict[str, Path]) -> None:
    """A patch that previously wrote file F is removed; reconcile restores F
    from upstream and removes the entry from the manifest."""
    _seed_upstream(sandbox["upstream"], {"src/a.ts": "upstream-a\n", "src/b.ts": "upstream-b\n"})
    _seed_ui(sandbox["ui"], {"src/a.ts": "upstream-a\n", "src/b.ts": "patched-b\n"})

    manifest = Manifest()
    manifest.patches["vanished_patch"] = PatchEntry(
        name="vanished_patch",
        status="applied",
        source_sha="deadbeef",
        written=["src/b.ts"],
    )
    _write_manifest(manifest)

    results = reconcile(modules=[])

    assert any(r.status == "orphan_restored" and r.name == "vanished_patch" for r in results)
    assert (sandbox["ui"] / "src/b.ts").read_text() == "upstream-b\n"

    new_manifest = _read_manifest()
    assert "vanished_patch" not in new_manifest.patches


# ── Quadrant 2: declared-but-unrecorded → restore + re-apply ──────────


def test_declared_divergence_restores_before_reapply(
    sandbox: dict[str, Path],
) -> None:
    """A registered patch declares a file, lobehub-ui has it modified, but
    the manifest has no record of it (e.g. manifest was wiped). Reconcile
    must restore the file from upstream and the next apply must write the
    fresh content."""
    _seed_upstream(sandbox["upstream"], {"src/x.ts": "upstream-x\n"})
    _seed_ui(sandbox["ui"], {"src/x.ts": "stale-write-by-ghost\n"})

    patch = _patch("ghost", "fresh-by-patch\n", files=("src/x.ts",))

    reconcile(modules=[patch])

    assert (sandbox["ui"] / "src/x.ts").read_text() == "upstream-x\n"

    # Now apply — should write the patch's body
    ctx = PatchContext(ui_dir=sandbox["ui"], manifest=_read_manifest())
    ctx._current_patch = "ghost"
    patch.apply(ctx)
    _write_manifest(ctx._manifest)
    assert (sandbox["ui"] / "src/x.ts").read_text() == "fresh-by-patch\n"


# ── Quadrant 3: stale source → restore + re-apply ─────────────────────


def test_stale_source_sha_restores_then_reapplies(
    sandbox: dict[str, Path],
) -> None:
    """A registered patch whose source_sha changed must have its writes
    restored and then be re-applied."""
    _seed_upstream(sandbox["upstream"], {"src/y.ts": "upstream-y\n"})
    _seed_ui(sandbox["ui"], {"src/y.ts": "upstream-y\n"})

    manifest = Manifest()
    manifest.patches["mutating"] = PatchEntry(
        name="mutating",
        status="applied",
        source_sha="old-hash",
        written=["src/y.ts"],
    )
    _write_manifest(manifest)

    patch = _patch("mutating", "fresh-content\n", files=("src/y.ts",))

    reconcile(modules=[patch])
    assert (sandbox["ui"] / "src/y.ts").read_text() == "upstream-y\n"

    ctx = PatchContext(ui_dir=sandbox["ui"], manifest=_read_manifest())
    ctx._current_patch = "mutating"
    patch.apply(ctx)
    # Simulate what apply_patches does after the call: refresh source_sha.
    ctx._manifest.patches["mutating"].source_sha = _compute_patch_hash(patch)
    _write_manifest(ctx._manifest)
    assert (sandbox["ui"] / "src/y.ts").read_text() == "fresh-content\n"
    assert _read_manifest().patches["mutating"].source_sha != "old-hash"


# ── Quadrant 4: cold-start orphan sweep ───────────────────────────────


def test_cold_start_sweep_restores_files_with_no_manifest(
    sandbox: dict[str, Path],
) -> None:
    """Empty manifest + divergent files in lobehub-ui not claimed by any
    patch = a previous patch was reverted. Sweep restores them. This is the
    exact regression that the inspector_shiny_text_legibility revert exposed."""
    _seed_upstream(sandbox["upstream"], {"src/styles/loading.ts": "upstream-45%\n"})
    _seed_ui(
        sandbox["ui"],
        {"src/styles/loading.ts": "patched-70%\n/* lca-patch:legacy */\n"},
    )

    results = reconcile(modules=[])

    assert any(r.status == "orphan_restored" for r in results)
    on_disk = (sandbox["ui"] / "src/styles/loading.ts").read_text()
    assert on_disk == "upstream-45%\n"
    assert "lca-patch:legacy" not in on_disk


def test_cold_start_declared_divergence_is_restored(
    sandbox: dict[str, Path],
) -> None:
    """Cold start + a current patch declares a file that diverges from
    upstream → we have no record of who wrote it, so restore and let
    apply() redo. Same rule as the orphan sweep; just exercised via the
    declared-divergence branch instead of the bare file-diff branch."""
    _seed_upstream(sandbox["upstream"], {"src/d.ts": "upstream-d\n"})
    _seed_ui(sandbox["ui"], {"src/d.ts": "mystery-write\n"})

    patch = _patch("live", "live-body\n", files=("src/d.ts",))

    reconcile(modules=[patch])

    # File is restored from upstream; apply() will write the live body next.
    assert (sandbox["ui"] / "src/d.ts").read_text() == "upstream-d\n"


# ── Manifest self-consistency ─────────────────────────────────────────


def test_patchcontext_records_writes(sandbox: dict[str, Path]) -> None:
    _seed_ui(sandbox["ui"], {})
    manifest = Manifest()
    ctx = PatchContext(ui_dir=sandbox["ui"], manifest=manifest)
    ctx._current_patch = "alpha"
    ctx.write("src/alpha.ts", "alpha body\n")
    ctx.write_if_changed("src/alpha.ts", "alpha body\n")  # no-op
    ctx.write_if_changed("src/beta.ts", "beta body\n")
    ctx._current_patch = "gamma"
    ctx.write("src/gamma.ts", "gamma body\n")

    assert manifest.patches["alpha"].written == ["src/alpha.ts", "src/beta.ts"]
    assert manifest.patches["gamma"].written == ["src/gamma.ts"]


def test_patchcontext_no_owner_does_not_record(sandbox: dict[str, Path]) -> None:
    """Writes outside a patch invocation are not tracked."""
    _seed_ui(sandbox["ui"], {})
    manifest = Manifest()
    ctx = PatchContext(ui_dir=sandbox["ui"], manifest=manifest)
    ctx.write("src/free.ts", "free\n")
    assert manifest.patches == {}


def test_manifest_roundtrip() -> None:
    original = Manifest(
        patched_at="2026-09-01T00:00:00+00:00",
        lobehub_release="v2.2.13",
    )
    original.patches["p"] = PatchEntry(
        name="p", status="applied", source_sha="abc", written=["x.ts", "y.ts"]
    )
    raw = original.to_json()
    restored = Manifest.from_json(raw)
    assert restored.patches["p"].written == ["x.ts", "y.ts"]
    assert restored.lobehub_release == "v2.2.13"


def test_manifest_migration_consumes_legacy_files(sandbox: dict[str, Path]) -> None:
    """Legacy .lca-patched + .lca-patch-hashes are migrated and deleted."""
    sandbox["ui"].mkdir(parents=True, exist_ok=True)
    (sandbox["ui"] / ".lca-patched").write_text(
        json.dumps({"patches": {"legacy_p": "applied"}}, indent=2)
    )
    (sandbox["ui"] / ".lca-patch-hashes").write_text(json.dumps({"legacy_p": "deadbeef"}))

    from deploy.lobehub.engine import _migrate_legacy_files

    migrated = _migrate_legacy_files()
    assert migrated
    assert not (sandbox["ui"] / ".lca-patched").exists()
    assert not (sandbox["ui"] / ".lca-patch-hashes").exists()

    manifest = _read_manifest()
    assert "legacy_p" in manifest.patches
    assert manifest.patches["legacy_p"].status == "applied"
    assert manifest.patches["legacy_p"].source_sha == "deadbeef"


def test_failed_import_is_not_treated_as_orphan(sandbox: dict[str, Path]) -> None:
    """A patch present on disk but failing to import must keep its writes."""
    _seed_upstream(sandbox["upstream"], {"src/q.ts": "upstream-q\n"})
    _seed_ui(sandbox["ui"], {"src/q.ts": "patched-q\n"})

    manifest = Manifest()
    manifest.patches["broken_import"] = PatchEntry(
        name="broken_import",
        status="applied",
        source_sha="abc",
        written=["src/q.ts"],
    )
    _write_manifest(manifest)

    # modules is empty (simulating import failure), failed_names says it's
    # still owned — must NOT be touched.
    results = reconcile(modules=[], failed_names=["broken_import"])

    assert not any(r.name == "broken_import" for r in results)
    assert (sandbox["ui"] / "src/q.ts").read_text() == "patched-q\n"
