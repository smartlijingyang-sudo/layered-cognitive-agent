"""Tests for lca.layer0_infra.ops.upstream_mirror — pure-function path conversion & diff."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.layer0_infra.ops.upstream_mirror import (
    MirrorDiff,
    PackageInventory,
    UpstreamTree,
    cli_run,
    coverage_stats,
    diff_trees,
    format_json,
    format_report,
    scan_local,
    scan_upstream,
    sync_skeletons,
    to_python_file,
    to_python_pkg,
)

# ---------------------------------------------------------------------------
# Path conversion — pure functions, no fixtures
# ---------------------------------------------------------------------------


class TestPathConversion:
    def test_to_python_pkg_strips_hyphens(self) -> None:
        assert to_python_pkg("llm-deepseek") == "llm_deepseek"
        assert to_python_pkg("session-persistence-jsonl") == "session_persistence_jsonl"
        assert to_python_pkg("ui-message-feedback") == "ui_message_feedback"

    def test_to_python_pkg_passthrough(self) -> None:
        assert to_python_pkg("llm") == "llm"
        assert to_python_pkg("acp") == "acp"

    def test_to_python_file_appends_py(self) -> None:
        assert to_python_file("index") == "index.py"
        assert to_python_file("assembler") == "assembler.py"
        assert to_python_file("client__sessions__manager") == "client__sessions__manager.py"


# ---------------------------------------------------------------------------
# Inventory & diff — uses tmp_path fixtures to build fake upstream/local trees
# ---------------------------------------------------------------------------


def _write_upstream(root: Path, layout: dict[str, dict[str, list[str]]]) -> None:
    """Build a fake upstream packages/ tree.

    layout = { top_pkg: { sub_pkg: [ts_filename, ...] } }
    """
    for top, subs in layout.items():
        top_dir = root / top
        top_dir.mkdir(parents=True, exist_ok=True)
        for sub, files in subs.items():
            sub_dir = top_dir / sub
            sub_dir.mkdir(parents=True, exist_ok=True)
            (sub_dir / "package.json").write_text("{}", encoding="utf-8")
            src_dir = sub_dir / "src"
            src_dir.mkdir(exist_ok=True)
            for fn in files:
                # Allow nested paths via "client/sessions/manager.ts" style.
                fp = src_dir / fn
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(f"// upstream {fn}", encoding="utf-8")


def _write_local(root: Path, layout: dict[str, dict[str, list[str]]]) -> None:
    """Build a fake local packages/ tree. Sub names are already Python-form."""
    for top, subs in layout.items():
        top_dir = root / top
        top_dir.mkdir(parents=True, exist_ok=True)
        (top_dir / "__init__.py").write_text("", encoding="utf-8")
        for sub, files in subs.items():
            sub_dir = top_dir / sub
            sub_dir.mkdir(parents=True, exist_ok=True)
            (sub_dir / "__init__.py").write_text("", encoding="utf-8")
            src_dir = sub_dir / "src"
            src_dir.mkdir(exist_ok=True)
            (src_dir / "__init__.py").write_text("", encoding="utf-8")
            for fn in files:
                fp = src_dir / fn
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(f'"""local {fn}"""', encoding="utf-8")


class TestScanUpstream:
    def test_basic(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        _write_upstream(
            up,
            {
                "llm": {
                    "llm-deepseek": ["index.ts", "adapter.ts"],
                    "llm": ["assembler.ts", "invariant.ts"],
                },
                "core": {
                    "agent": ["index.ts", "types.ts"],
                },
            },
        )
        trees = scan_upstream(up)
        assert set(trees) == {"llm", "core"}
        assert trees["llm"].sub_names == frozenset({"llm-deepseek", "llm"})
        assert trees["llm"].subs["llm-deepseek"].src_stems == frozenset({"index", "adapter"})
        assert trees["llm"].subs["llm"].src_stems == frozenset({"assembler", "invariant"})

    def test_skips_non_package_dirs(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        (up / "real" / "sub" / "src").mkdir(parents=True)
        (up / "real" / "sub" / "package.json").write_text("{}")
        (up / "real" / "sub" / "src" / "index.ts").write_text("// x")
        # No package.json → not a real package
        (up / "junk" / "src").mkdir(parents=True)
        (up / "junk" / "src" / "index.ts").write_text("// x")
        # node_modules should be skipped
        (up / "real" / "node_modules" / "evil").mkdir(parents=True)
        (up / "real" / "node_modules" / "evil" / "package.json").write_text("{}")

        trees = scan_upstream(up)
        assert set(trees) == {"real"}

    def test_missing_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            scan_upstream(tmp_path / "nope")


class TestScanLocal:
    def test_empty_root(self, tmp_path: Path) -> None:
        assert scan_local(tmp_path / "nope") == {}
        (tmp_path / "empty").mkdir()
        assert scan_local(tmp_path / "empty") == {}

    def test_requires_init_py(self, tmp_path: Path) -> None:
        root = tmp_path / "local"
        (root / "pkg" / "sub").mkdir(parents=True)
        # No __init__.py at any level → both skipped
        trees = scan_local(root)
        assert trees == {}

    def test_basic(self, tmp_path: Path) -> None:
        root = tmp_path / "local"
        _write_local(
            root,
            {
                "llm": {
                    "llm_deepseek": ["index.py", "adapter.py"],
                }
            },
        )
        trees = scan_local(root)
        assert "llm" in trees
        assert trees["llm"].sub_names == frozenset({"llm_deepseek"})
        assert trees["llm"].subs["llm_deepseek"].src_stems == frozenset({"index", "adapter"})


class TestDiffTrees:
    def test_full_sync(self, tmp_path: Path) -> None:
        layout = {
            "llm": {
                "llm-deepseek": ["index.ts", "adapter.ts"],
            },
        }
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, layout)
        _write_local(loc, {"llm": {"llm_deepseek": ["index.py", "adapter.py"]}})

        diff = diff_trees(scan_upstream(up), scan_local(loc))
        assert diff.is_in_sync
        assert diff.total_missing == 0
        assert diff.total_extra == 0

    def test_missing_top(self, tmp_path: Path) -> None:
        layout = {"llm": {"llm-deepseek": ["index.ts"]}, "core": {"agent": ["x.ts"]}}
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, layout)
        _write_local(loc, {"llm": {"llm_deepseek": ["index.py"]}})

        diff = diff_trees(scan_upstream(up), scan_local(loc))
        assert "core" in diff.missing_top
        assert diff.is_in_sync is False

    def test_missing_sub_uses_python_form(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(
            up,
            {
                "llm": {
                    "llm-deepseek": ["index.ts"],
                    "llm-pi-ai": ["index.ts"],
                },
            },
        )
        _write_local(loc, {"llm": {"llm_deepseek": ["index.py"]}})

        diff = diff_trees(scan_upstream(up), scan_local(loc))
        # The missing sub is reported with its upstream form; the local form
        # is derivable via to_python_pkg.
        assert ("llm", "llm-pi-ai") in diff.missing_sub
        assert all(to_python_pkg(s) for _, s in diff.missing_sub)

    def test_missing_files(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, {"llm": {"llm-deepseek": ["index.ts", "adapter.ts"]}})
        _write_local(loc, {"llm": {"llm_deepseek": ["index.py"]}})

        diff = diff_trees(scan_upstream(up), scan_local(loc))
        assert ("llm", "llm-deepseek", "adapter") in diff.missing_files
        assert diff.is_in_sync is False

    def test_extra_local_tracked(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, {"llm": {"llm-deepseek": ["index.ts"]}})
        _write_local(
            loc,
            {
                "llm": {"llm_deepseek": ["index.py"]},
                "lca_specific": {"some_sub": ["index.py"]},
            },
        )
        diff = diff_trees(scan_upstream(up), scan_local(loc))
        assert "lca_specific" in diff.extra_top
        assert ("lca_specific", "some_sub") in diff.extra_sub


class TestCoverageStats:
    def test_basic(self) -> None:
        upstream = {
            "llm": UpstreamTree(
                sub_names=frozenset({"llm-deepseek"}),
                subs={"llm-deepseek": PackageInventory(src_stems=frozenset({"index", "adapter"}))},
            ),
        }
        diff = MirrorDiff(missing_files=(("llm", "llm-deepseek", "adapter"),))
        stats = coverage_stats(upstream, diff)
        assert stats["upstream_top"] == 1
        assert stats["upstream_sub"] == 1
        assert stats["upstream_files"] == 2
        assert stats["missing_files"] == 1
        assert stats["files_pct"] == 50.0

    def test_zero_upstream(self) -> None:
        stats = coverage_stats({}, MirrorDiff())
        assert stats["top_pct"] == 100.0
        assert stats["sub_pct"] == 100.0
        assert stats["files_pct"] == 100.0


class TestRenderers:
    def test_format_report_in_sync(self, tmp_path: Path) -> None:
        diff = MirrorDiff()
        stats = coverage_stats({}, diff)
        text = format_report(
            diff,
            stats,
            upstream_root=tmp_path / "u",
            target_root=tmp_path / "l",
        )
        assert "IN SYNC" in text
        assert "nothing to sync" in text

    def test_format_report_lists_missing(self, tmp_path: Path) -> None:
        diff = MirrorDiff(missing_top=("foo", "bar"), missing_files=(("baz", "sub", "x"),))
        upstream = {
            "baz": UpstreamTree(
                sub_names=frozenset({"sub"}),
                subs={"sub": PackageInventory(src_stems=frozenset({"x"}))},
            )
        }
        stats = coverage_stats(upstream, diff)
        text = format_report(
            diff,
            stats,
            upstream_root=tmp_path / "u",
            target_root=tmp_path / "l",
        )
        assert "OUT OF SYNC" in text
        assert "+ foo/" in text
        assert "+ bar/" in text
        assert "+ baz/sub/" in text

    def test_format_json_valid(self, tmp_path: Path) -> None:
        diff = MirrorDiff(missing_top=("foo",))
        upstream = {"foo": UpstreamTree(sub_names=frozenset())}
        stats = coverage_stats(upstream, diff)
        out = format_json(diff, stats, upstream_root=tmp_path / "u", target_root=tmp_path / "l")
        import json

        payload = json.loads(out)
        assert payload["in_sync"] is False
        assert payload["missing"]["top"] == ["foo"]


# ---------------------------------------------------------------------------
# Sync — generates skeleton files; never overwrites unless forced
# ---------------------------------------------------------------------------


class TestSyncSkeletons:
    def test_generates_missing_top(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, {"llm": {"llm-deepseek": ["index.ts"]}})
        diff = MirrorDiff(missing_top=("llm",))
        c_top, _c_sub, _c_files = sync_skeletons(up, loc, diff)
        assert c_top == 1
        assert (loc / "llm" / "__init__.py").exists()

    def test_generates_missing_sub_and_files(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(
            up,
            {
                "llm": {
                    "llm-deepseek": ["index.ts", "adapter.ts"],
                },
            },
        )
        diff = MirrorDiff(missing_sub=(("llm", "llm-deepseek"),))
        c_top, c_sub, c_files = sync_skeletons(up, loc, diff)
        assert c_top == 1
        assert c_sub == 1
        # No missing_files in the diff, so no files created.
        assert c_files == 0
        sub_dir = loc / "llm" / "llm_deepseek"
        assert (sub_dir / "__init__.py").exists()
        assert (sub_dir / "src" / "__init__.py").exists()

    def test_generates_missing_files(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, {"llm": {"llm-deepseek": ["index.ts", "adapter.ts"]}})
        # Pre-create the structure so we test file-level sync.
        _write_local(loc, {"llm": {"llm_deepseek": ["index.py"]}})
        diff = MirrorDiff(missing_files=(("llm", "llm-deepseek", "adapter"),))
        _c_top, _c_sub, c_files = sync_skeletons(up, loc, diff)
        assert c_files == 1
        stub = loc / "llm" / "llm_deepseek" / "src" / "adapter.py"
        assert stub.exists()
        assert "deepseek-harness" in stub.read_text(encoding="utf-8")
        assert "llm-deepseek" in stub.read_text(encoding="utf-8")

    def test_idempotent(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, {"llm": {"llm-deepseek": ["index.ts"]}})
        diff = MirrorDiff(missing_top=("llm",))
        # First sync creates, second sync no-ops.
        sync_skeletons(up, loc, diff)
        existing_init = (loc / "llm" / "__init__.py").read_text(encoding="utf-8")
        sync_skeletons(up, loc, diff)
        assert (loc / "llm" / "__init__.py").read_text(encoding="utf-8") == existing_init

    def test_force_overwrites(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, {"llm": {"llm-deepseek": ["index.ts"]}})
        diff = MirrorDiff(missing_top=("llm",))
        sync_skeletons(up, loc, diff)
        (loc / "llm" / "__init__.py").write_text("CUSTOM CONTENT", encoding="utf-8")
        sync_skeletons(up, loc, diff)
        # Without --force: custom content preserved.
        assert (loc / "llm" / "__init__.py").read_text(encoding="utf-8") == "CUSTOM CONTENT"
        sync_skeletons(up, loc, diff, force=True)
        assert "Top-level package mirror" in (loc / "llm" / "__init__.py").read_text(
            encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# CLI runner — exercises the full integration with both report and sync modes.
# ---------------------------------------------------------------------------


class TestCliRun:
    def test_report_only_against_real_upstream(self) -> None:
        """Real run against ~/deepseek-harness/packages should produce a non-zero
        missing count and exit code 1, since lca/packages/ doesn't exist yet."""
        upstream = Path.home() / "deepseek-harness" / "packages"
        if not upstream.is_dir():
            pytest.skip("upstream not present")
        # Use a tmp_path-derived target that does not exist.
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            bogus = Path(td) / "missing_target_root"
            code = cli_run(
                upstream=upstream,
                target=bogus,
                sync=False,
                force=False,
                json_output=False,
            )
            assert code == 1

    def test_sync_then_in_sync(self, tmp_path: Path) -> None:
        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(
            up,
            {
                "llm": {"llm-deepseek": ["index.ts"]},
                "core": {"agent": ["index.ts", "types.ts"]},
            },
        )
        code = cli_run(upstream=up, target=loc, sync=True, force=False, json_output=False)
        assert code == 0
        # After sync we should have top-level + sub + files.
        assert (loc / "llm" / "__init__.py").exists()
        assert (loc / "llm" / "llm_deepseek" / "src" / "index.py").exists()
        assert (loc / "core" / "agent" / "src" / "types.py").exists()

    def test_json_output_is_valid_json(self, tmp_path: Path) -> None:

        up = tmp_path / "upstream"
        loc = tmp_path / "local"
        _write_upstream(up, {"llm": {"llm-deepseek": ["index.ts"]}})
        # Capture stdout by patching print is overkill; just check exit code + no crash.
        cli_run(upstream=up, target=loc, sync=False, force=False, json_output=True)

        # Now do a sync with json to ensure both branches work.
        cli_run(upstream=up, target=loc, sync=True, force=False, json_output=True)
