"""LobeHub Patch Engine — modular, auto-discovered, declarative-friendly.

Architecture:
    deploy/lobehub/
    ├── patch_lobehub.py          # thin CLI entry point
    ├── engine.py                 # this file — core types + engine + CLI
    └── patches/                  # auto-discovered patch modules
        ├── streaming/openai_stream.py
        ├── runtime/streaming_handler.py
        └── ...

Each patch module exports:
    meta: PatchMeta               # declarative metadata
    apply(ctx: PatchContext) -> bool  # apply logic; True = applied, False = skipped

Usage:
    python3 deploy/lobehub/patch_lobehub.py              # apply all
    python3 deploy/lobehub/patch_lobehub.py verify       # check markers
    python3 deploy/lobehub/patch_lobehub.py list         # show manifest
    python3 deploy/lobehub/patch_lobehub.py drift        # detect unregistered edits
    python3 deploy/lobehub/patch_lobehub.py manifest     # JSON manifest
    python3 deploy/lobehub/patch_lobehub.py doctor       # full health check
    python3 deploy/lobehub/patch_lobehub.py apply openai_stream protocol  # specific
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import pkgutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "lobehub-ui"
STAMP_FILE = UI / ".lca-patched"
HASH_FILE = UI / ".lca-patch-hashes"  # per-patch source hashes
_UPSTREAM = ROOT / ".lobehub-upstream"

# ── Types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PatchMeta:
    name: str
    description: str
    files: tuple[str, ...]
    risk: str
    category: str
    depends_on: tuple[str, ...] = ()
    why: str = ""
    technical_detail: str = ""
    verify_file: str = ""
    verify_marker: str = ""


@dataclass
class PatchResult:
    name: str
    status: str  # applied | skipped | ok | broken | missing_file
    detail: str = ""


PatchFunc = Callable[["PatchContext"], bool]


@dataclass
class PatchModule:
    meta: PatchMeta
    apply: PatchFunc


# ── PatchContext ───────────────────────────────────────────────────────


class PatchContext:
    """Provides file I/O and string manipulation helpers for patch modules."""

    def __init__(self, ui_dir: Path = UI) -> None:
        self._ui = ui_dir

    def path(self, rel: str) -> Path:
        return self._ui / rel

    def read(self, rel: str) -> str:
        p = self.path(rel)
        if not p.is_file():
            raise FileNotFoundError(f"missing {p} — run ./scripts/sync_lobehub_ui.sh first")
        return p.read_text()

    def write(self, rel: str, text: str) -> None:
        self.path(rel).write_text(text)

    def write_if_changed(self, rel: str, text: str) -> bool:
        """Write file only when content differs. Returns True if written."""
        p = self.path(rel)
        try:
            current = p.read_text()
        except FileNotFoundError:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            return True
        if current != text:
            p.write_text(text)
            return True
        return False

    def has_marker(self, rel: str, marker: str) -> bool:
        try:
            return marker in self.read(rel)
        except FileNotFoundError:
            return False

    def replace_once(self, rel: str, anchor: str, insert: str, *, label: str = "") -> str:
        """Find anchor in file, replace with insert (first occurrence only)."""
        text = self.read(rel)
        if anchor not in text:
            tag = label or rel
            raise SystemExit(f"[{tag}] anchor not found")
        return text.replace(anchor, insert, 1)

    def replace_all(self, rel: str, old: str, new: str) -> str:
        text = self.read(rel)
        return text.replace(old, new)

    def create_file(self, rel: str, content: str) -> bool:
        """Create file if it doesn't exist. Returns True if created."""
        p = self.path(rel)
        if p.is_file():
            return False
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return True


# ── Auto-Discovery ─────────────────────────────────────────────────────


def discover_patches() -> list[PatchModule]:
    """Scan patches/ directory, import modules, collect PatchMeta + apply."""
    import deploy.lobehub.patches as patches_pkg

    modules: list[PatchModule] = []
    pkg_path = patches_pkg.__path__

    for _importer, modname, _ispkg in pkgutil.walk_packages(
        pkg_path, prefix="deploy.lobehub.patches."
    ):
        # Skip __init__ and non-patch modules
        if modname.endswith(".__init__"):
            continue
        try:
            mod = importlib.import_module(modname)
        except Exception as exc:
            print(f"[discovery] WARNING: failed to import {modname}: {exc}", file=sys.stderr)
            continue

        meta = getattr(mod, "meta", None)
        apply_fn = getattr(mod, "apply", None)
        if meta is None or apply_fn is None:
            continue
        if not isinstance(meta, PatchMeta):
            print(f"[discovery] WARNING: {modname}.meta is not PatchMeta", file=sys.stderr)
            continue
        modules.append(PatchModule(meta=meta, apply=apply_fn))

    return modules


# ── Engine ─────────────────────────────────────────────────────────────


def _filter(modules: list[PatchModule], names: tuple[str, ...]) -> list[PatchModule]:
    if not names:
        return list(modules)
    by_name = {m.meta.name: m for m in modules}
    selected = []
    for n in names:
        if n not in by_name:
            available = ", ".join(sorted(by_name))
            raise SystemExit(f"unknown patch: {n}\nAvailable: {available}")
        selected.append(by_name[n])
    return selected


def apply_patches(names: tuple[str, ...] = (), *, reset: bool = False) -> list[PatchResult]:
    if not UI.is_dir():
        print("[patch] skip: lobehub-ui/ missing", file=sys.stderr)
        sys.exit(0)

    modules = discover_patches()
    patches = _filter(modules, names)

    # ── Detect source changes & auto-restore ──
    current_hashes = {pm.meta.name: _compute_patch_hash(pm) for pm in patches}
    old_hashes = _load_hashes()
    changed_names = {name for name, h in current_hashes.items() if old_hashes.get(name) != h}

    need_restore = bool(changed_names) or reset
    if need_restore:
        # 只还原即将重新 apply 的 patch 的目标文件，不碰其他 patch 的文件
        rels = _all_patch_target_files(patches)
        restored = _restore_from_upstream(rels)
        _clear_stamps()
        if changed_names and not reset:
            _log(
                "RESTORE",
                ",".join(sorted(changed_names)),
                f"{restored} files restored from upstream",
            )
        elif reset:
            scope = ",".join(sorted(m.meta.name for m in patches)) if names else "all"
            _log("RESET", scope, f"{restored} files restored from upstream")

    results: list[PatchResult] = []
    applied_count = 0
    ctx = PatchContext()

    for pm in patches:
        try:
            was_applied = pm.apply(ctx)
        except SystemExit as exc:
            results.append(PatchResult(pm.meta.name, "broken", str(exc)))
            _log("BROKEN", pm.meta.name, str(exc))
            continue
        status = "applied" if was_applied else "skipped"
        if was_applied:
            applied_count += 1
        results.append(PatchResult(pm.meta.name, status))
        _log(status.upper(), pm.meta.name)

    _write_stamp(results)
    _save_hashes(current_hashes)
    print(f"\n[patch] done: {applied_count} applied, {len(results) - applied_count} skipped")
    return results


def verify_patches(names: tuple[str, ...] = ()) -> list[PatchResult]:
    if not UI.is_dir():
        print("[verify] skip: lobehub-ui/ missing", file=sys.stderr)
        sys.exit(0)

    modules = discover_patches()
    patches = _filter(modules, names)
    ctx = PatchContext()
    results: list[PatchResult] = []
    ok_count = 0
    broken_count = 0

    for pm in patches:
        meta = pm.meta
        if not meta.verify_marker:
            results.append(PatchResult(meta.name, "ok", "no verify marker"))
            _log("SKIP", meta.name, "no verify marker")
            continue
        check_file = meta.verify_file or (meta.files[0] if meta.files else "")
        if not check_file:
            results.append(PatchResult(meta.name, "ok", "no verify file"))
            continue
        path = ctx.path(check_file)
        if not path.is_file():
            results.append(PatchResult(meta.name, "missing_file", f"{check_file} not found"))
            _log("MISS", meta.name, f"{check_file} not found")
            broken_count += 1
            continue
        if meta.verify_marker in path.read_text():
            results.append(PatchResult(meta.name, "ok", "marker present"))
            _log("OK", meta.name)
            ok_count += 1
        else:
            results.append(PatchResult(meta.name, "broken", f"marker absent in {check_file}"))
            _log("BROKEN", meta.name, f"marker absent in {check_file}")
            broken_count += 1

    print(f"\n[verify] {ok_count} ok, {broken_count} broken/missing")
    return results


def list_patches(*, verbose: bool = False) -> None:
    modules = discover_patches()
    print(f"{'#':>2}  {'Name':<28} {'Risk':<6} {'Category':<10} Description")
    print("─" * 100)
    for i, pm in enumerate(modules, 1):
        meta = pm.meta
        deps = f" ← {','.join(meta.depends_on)}" if meta.depends_on else ""
        print(
            f"{i:>2}  {meta.name:<28} {meta.risk:<6} {meta.category:<10} {meta.description}{deps}"
        )
        if verbose and meta.why:
            print(f"     why: {meta.why}")
        if verbose and meta.technical_detail:
            print(f"     how: {meta.technical_detail}")
    cats = {m.meta.category for m in modules}
    print(f"\nTotal: {len(modules)} patches across {len(cats)} categories")
    print(f"Upstream: LobeHub {_read_origin_release()}")
    print("Commands: apply | verify | list [--verbose] | drift | manifest | doctor")


# ── Drift Guard ────────────────────────────────────────────────────────

_DRIFT_IGNORE = frozenset(
    {
        ".env",
        ".lca-patched",
        ".lca-patch-hashes",
        ".lca-integration-patched",
        ".lca-qwen-defaults-patched",
        ".lca-origin.json",
        "next-env.d.ts",
    }
)

_DRIFT_IGNORE_PREFIXES = (
    "node_modules/",
    ".next/",
    ".turbo/",
    "dist/",
    "coverage/",
    ".git/",
    "public/_spa/",
    "public/_spa-auth/",
    ".pytest_cache/",
    "docker-compose/dev/data/",
    ".agent-tracing/",
    ".llm-generation-tracing/",
)


def _collect_covered_files(modules: list[PatchModule]) -> set[str]:
    covered: set[str] = set()
    for pm in modules:
        covered.update(pm.meta.files)
    return covered


def _is_ignored(rel: str) -> bool:
    if rel in _DRIFT_IGNORE:
        return True
    if any(rel.startswith(p) for p in _DRIFT_IGNORE_PREFIXES):
        return True
    return "/node_modules/" in rel or rel.endswith("/node_modules")


def drift_guard(*, verbose: bool = False) -> list[str]:
    if not _UPSTREAM.is_dir():
        return [f"upstream cache not found: {_UPSTREAM}"]
    if not UI.is_dir():
        return [f"lobehub-ui/ not found: {UI}"]

    modules = discover_patches()
    covered = _collect_covered_files(modules)
    violations: list[str] = []

    for path in UI.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(UI))
        if _is_ignored(rel):
            continue
        upstream_path = _UPSTREAM / rel
        if not upstream_path.is_file():
            if rel not in covered:
                violations.append(f"NEW FILE (not in any patch): {rel}")
            continue
        try:
            if path.read_bytes() == upstream_path.read_bytes():
                continue
        except OSError:
            continue
        if rel not in covered:
            violations.append(f"MODIFIED (not in any patch): {rel}")

    if verbose:
        if violations:
            print(f"\n[drift] ❌ {len(violations)} unregistered modification(s):")
            for v in violations:
                print(f"  • {v}")
            print("\n[drift] FIX: register these changes as patches in patches/")
            print("[drift] Then run: python3 deploy/lobehub/patch_lobehub.py --reset")
        else:
            print("[drift] ✅ all modifications covered by registered patches")

    return violations


def generate_manifest() -> dict[str, Any]:
    modules = discover_patches()
    patches = []
    for i, pm in enumerate(modules, 1):
        meta = pm.meta
        patches.append(
            {
                "index": i,
                "name": meta.name,
                "description": meta.description,
                "category": meta.category,
                "risk": meta.risk,
                "files": list(meta.files),
                "depends_on": list(meta.depends_on),
                "why": meta.why,
                "technical_detail": meta.technical_detail,
                "verify_marker": meta.verify_marker or None,
            }
        )
    return {
        "schema_version": 2,
        "upstream_release": _read_origin_release(),
        "total_patches": len(modules),
        "categories": sorted({pm.meta.category for pm in modules}),
        "patches": patches,
    }


def doctor() -> int:
    print("=" * 60)
    print("  LobeHub Patch Doctor")
    print("=" * 60)

    issues = 0

    print("\n── 1. Patch markers ──")
    verify_results = verify_patches()
    broken = [r for r in verify_results if r.status == "broken"]
    issues += len(broken)

    print("\n── 2. Drift guard ──")
    drift_violations = drift_guard(verbose=True)
    issues += len(drift_violations)

    print("\n── 3. Dependency graph ──")
    modules = discover_patches()
    all_names = {pm.meta.name for pm in modules}
    for pm in modules:
        for dep in pm.meta.depends_on:
            if dep not in all_names:
                print(f"  ❌ {pm.meta.name}: depends on unknown patch '{dep}'")
                issues += 1

    print("\n" + "=" * 60)
    if issues == 0:
        print("  ✅ All checks passed")
    else:
        print(f"  ❌ {issues} issue(s) found")
    print("=" * 60)
    return issues


# ── CLI ────────────────────────────────────────────────────────────────

_COMMANDS = ("apply", "verify", "list", "drift", "manifest", "doctor")


def main() -> None:
    args = sys.argv[1:]
    cmd = "apply"
    names: list[str] = []
    reset = False
    verbose = False

    i = 0
    while i < len(args):
        a = args[i]
        if a in _COMMANDS:
            cmd = a
        elif a == "--reset":
            reset = True
        elif a in ("--verbose", "-v"):
            verbose = True
        elif a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            names.append(a)
        i += 1

    if cmd == "list":
        list_patches(verbose=verbose)
    elif cmd == "verify":
        results = verify_patches(tuple(names))
        broken_results = [r for r in results if r.status == "broken"]
        sys.exit(1 if broken_results else 0)
    elif cmd == "drift":
        violations = drift_guard(verbose=True)
        sys.exit(1 if violations else 0)
    elif cmd == "manifest":
        manifest = generate_manifest()
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    elif cmd == "doctor":
        issue_count = doctor()
        sys.exit(1 if issue_count else 0)
    else:
        results = apply_patches(tuple(names), reset=reset)
        broken_results = [r for r in results if r.status == "broken"]
        sys.exit(1 if broken_results else 0)


# ── Helpers ────────────────────────────────────────────────────────────


def _log(status: str, name: str, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    print(f"[patch] {status:<8} {name}{suffix}")


def _clear_stamps() -> None:
    for f in UI.glob(".lca-*-patched"):
        f.unlink()
    if STAMP_FILE.is_file():
        STAMP_FILE.unlink()


def _write_stamp(results: list[PatchResult]) -> None:
    stamp = {
        "patched_at": datetime.now(timezone.utc).isoformat(),
        "patches": {r.name: r.status for r in results},
        "lobehub_release": _read_origin_release(),
    }
    STAMP_FILE.write_text(json.dumps(stamp, indent=2, ensure_ascii=False) + "\n")


# ── Patch Source Hash & Snapshot ──────────────────────────────────────


def _compute_patch_hash(pm: PatchModule) -> str:
    """SHA-256 of the patch module's source file."""
    source_path = Path(inspect.getfile(pm.apply))
    return hashlib.sha256(source_path.read_bytes()).hexdigest()


def _load_hashes() -> dict[str, str]:
    if HASH_FILE.is_file():
        try:
            data = json.loads(HASH_FILE.read_text())
            if isinstance(data, dict):
                return {k: str(v) for k, v in data.items()}
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def _save_hashes(hashes: dict[str, str]) -> None:
    HASH_FILE.write_text(json.dumps(hashes, indent=2, ensure_ascii=False) + "\n")


def _all_patch_target_files(modules: list[PatchModule]) -> list[str]:
    """Collect unique target file rels across all patch modules."""
    seen: set[str] = set()
    result: list[str] = []
    for pm in modules:
        for rel in pm.meta.files:
            if rel not in seen:
                seen.add(rel)
                result.append(rel)
    return result


def _restore_from_upstream(rels: list[str]) -> int:
    """Restore target files from upstream cache to clean state. Returns count restored."""
    count = 0
    for rel in rels:
        upstream_file = _UPSTREAM / rel
        dst = UI / rel
        if upstream_file.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(upstream_file.read_bytes())
            count += 1
    return count


def _read_origin_release() -> str:
    origin = UI / ".lca-origin.json"
    if origin.is_file():
        try:
            data = json.loads(origin.read_text())
            if isinstance(data, dict):
                release = data.get("release")
                if isinstance(release, str):
                    return release
        except (json.JSONDecodeError, KeyError):
            pass
    return "unknown"
