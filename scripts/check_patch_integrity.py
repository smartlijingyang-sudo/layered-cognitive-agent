#!/usr/bin/env python3
"""Pre-commit hook: lobehub patch 完整性检查。

LobeHub UI 在本仓库是 gitignored，由 ``deploy/lobehub/engine.py:apply_patches``
从 ``deploy/lobehub/patches/<cat>/<file>.py`` 声明的 ``meta.files`` 自动同步。

维护 LCA patch 时容易踩两类坑：

1. ``meta.files`` 列了文件，但 ``deploy/lobehub/patches/<cat>/<sub>/<file>``
   实际不存在（且 patch 不是内联生成模式） —— ``apply()`` 静默跳过，
   lobehub-ui 下永远缺该文件。
2. TS/TSX 渲染器所需要的 shared component（``_shell.tsx`` 等）漏拷，
   import 解析失败，整个 renderer 模块加载失败但无明显报错。

此检查做三件事：

A. 调用每个 patch 的 ``apply(ctx)`` 拿到它写入 lobehub-ui 的实际内容。
B. 验证 lobehub-ui/ 下每个目标文件都已落地（patch apply 没漏掉）。
C. 验证 lobehub-ui/ 下每个目标文件 byte-for-byte 等于 patch 写入的内容
   （无手动漂移）。
"""

from __future__ import annotations

import importlib
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PATCHES_DIR = _ROOT / "deploy" / "lobehub" / "patches"
_UI_DIR = _ROOT / "lobehub-ui"

# When invoked as a plain script, Python's import machinery has no view of
# the ``deploy.*`` package.  Insert the repo root so module imports resolve.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class _CaptureCtx:
    """Minimal PatchContext that captures every ``write_if_changed`` so the
    check can diff the *intended* output against the actual file on disk.

    We don't run side effects — apply() is called with this ctx, every
    write is recorded, no file is touched.
    """

    def __init__(self) -> None:
        self.written: dict[str, str] = {}

    def path(self, rel: str) -> Path:
        return _UI_DIR / rel

    def read(self, rel: str) -> str:
        p = self.path(rel)
        if not p.is_file():
            raise FileNotFoundError(f"missing {p}")
        return p.read_text()

    def write(self, rel: str, text: str) -> None:
        self.written[rel] = text

    def write_if_changed(self, rel: str, text: str) -> bool:
        self.written[rel] = text
        # We can't reliably know whether the engine considered this changed
        # without running for real; report True so the check still flags drift.
        return True

    def has_marker(self, rel: str, marker: str) -> bool:  # pragma: no cover
        try:
            return marker in self.read(rel)
        except FileNotFoundError:
            return False


def _iter_patches():
    out: list[tuple[Path, object]] = []
    for f in sorted(_PATCHES_DIR.glob("**/*.py")):
        if f.name in {"__init__.py", "engine.py", "patch_lobehub.py"}:
            continue
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(_PATCHES_DIR)
        module_path = "deploy.lobehub.patches." + ".".join(rel.with_suffix("").parts)
        try:
            mod = importlib.import_module(module_path)
        except Exception as exc:
            out.append((f, exc))
            continue
        meta = getattr(mod, "meta", None)
        if meta is None:
            continue
        out.append((f, meta))
    return out


def main() -> int:
    patches = _iter_patches()
    if not patches:
        print("no patches discovered under", _PATCHES_DIR)
        return 0

    missing_in_ui: list[str] = []
    drifted: list[str] = []
    import_errors: list[str] = []
    files_total = 0

    for patch_file, meta in patches:
        if isinstance(meta, Exception):
            import_errors.append(f"{patch_file.name}: import error: {meta}")
            continue
        mod = importlib.import_module(
            "deploy.lobehub.patches."
            + ".".join(patch_file.relative_to(_PATCHES_DIR).with_suffix("").parts)
        )
        ctx = _CaptureCtx()
        # Run apply() with our capture ctx.  Swallow its print() output so
        # the check stays terse; failures surface via captured state.
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                mod.apply(ctx)
        except Exception as exc:
            import_errors.append(f"{patch_file.name}: apply() raised: {exc}")
            continue

        # Verify each declared meta.files target.
        for target in meta.files:
            files_total += 1
            ui_path = _UI_DIR / target
            # Did apply() actually write it?
            intended = ctx.written.get(target)
            if intended is None:
                # apply() may not write every meta.files (e.g. inline-only or
                # "skip if not present").  We still need it on disk to keep
                # the registry consistent.
                if not ui_path.is_file():
                    missing_in_ui.append(f"{patch_file.name}: {target}")
                continue
            if not ui_path.is_file():
                missing_in_ui.append(f"{patch_file.name}: {target}")
                continue
            actual = ui_path.read_text()
            if actual != intended:
                drifted.append(f"{patch_file.name}: {target}")

    ok = not (missing_in_ui or drifted or import_errors)
    if ok:
        print(
            f"OK: {len(patches)} patches, {files_total} target files — "
            "all source / deployed / byte-identical"
        )
        return 0

    if import_errors:
        print("patch import errors:")
        for line in import_errors:
            print(f"  {line}")
    if missing_in_ui:
        print("meta.files targets missing from lobehub-ui (re-run apply_patches):")
        for line in missing_in_ui:
            print(f"  {line}")
    if drifted:
        print("lobehub-ui drift from patch output (re-run apply_patches):")
        for line in drifted:
            print(f"  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
