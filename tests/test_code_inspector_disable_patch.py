"""Regression: the code_inspector_disable patch must (a) be discovered by
``discover_patches()`` so it ships in ``patch_lobehub.py apply``,
(b) replace the inspector plugin entry without altering other plugins,
and (c) be idempotent under re-application.
"""

from __future__ import annotations

import importlib
import importlib.util
import tempfile
from pathlib import Path

import pytest

from deploy.lobehub.engine import discover_patches
from deploy.lobehub.patches.devux.code_inspector_disable import apply, meta

# Load the actual upstream source so the needle in this test matches what
# the patch engine targets in production. ``.lobehub-upstream/`` is the
# pristine v2.2.13 tree that the patch engine treats as ground truth.
_UPSTREAM_PATH = Path(".lobehub-upstream/plugins/vite/sharedRendererConfig.ts")


def _load_upstream() -> str:
    if not _UPSTREAM_PATH.is_file():
        pytest.skip(f"upstream source not present at {_UPSTREAM_PATH}")
    return _UPSTREAM_PATH.read_text(encoding="utf-8")


def _build_context(tmp: Path, source: str) -> object:
    """Stand up a PatchContext whose read/write goes to a sandboxed tree."""

    src_dir = tmp / "lobehub-ui-src"
    target = src_dir / "plugins" / "vite" / "sharedRendererConfig.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")

    class _Ctx:
        @staticmethod
        def read(rel: str) -> str:
            return (src_dir / rel).read_text(encoding="utf-8")

        @staticmethod
        def write(rel: str, content: str) -> None:
            (src_dir / rel).write_text(content, encoding="utf-8")

        @staticmethod
        def write_if_changed(rel: str, content: str) -> bool:
            full = src_dir / rel
            if full.exists() and full.read_text(encoding="utf-8") == content:
                return False
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return True

    return _Ctx()


def test_patch_is_registered_in_discovery() -> None:
    # A missing import (e.g. runtime.lca_run_driver pulling in 'gateway')
    # can short-circuit discovery during test collection. Force-load our
    # module so the test asserts the registry regardless of that noise.
    importlib.import_module("deploy.lobehub.patches.devux.code_inspector_disable")
    names = {entry.meta.name for entry in discover_patches()}
    assert meta.name in names, names


def test_apply_replaces_inspector_with_null_marker() -> None:
    upstream = _load_upstream()
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _build_context(Path(tmp), upstream)
        assert apply(ctx) is True
        after = (
            Path(tmp) / "lobehub-ui-src" / "plugins" / "vite" / "sharedRendererConfig.ts"
        ).read_text(encoding="utf-8")
        assert "// LCA: code-inspector disabled" in after
        # The plugin call (the runtime entry point that binds 5678) must
        # disappear from the plugin array. The unused import line can
        # stay — it is tree-shaken in production builds.
        assert "codeInspectorPlugin({\n" not in after
        assert "codeInspectorPlugin({" not in after
        # Surrounding plugins stay intact (react remains in the array).
        assert "react()," in after
        # The platform branch for lobeIconImports is preserved verbatim.
        assert "lobeIconImports" in after


def test_apply_is_idempotent() -> None:
    upstream = _load_upstream()
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _build_context(Path(tmp), upstream)
        assert apply(ctx) is True
        # Second application must report no change (already disabled).
        assert apply(ctx) is False
