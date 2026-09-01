"""LobeHub Patch Engine — manifest-driven, auto-reconciling.

Architecture:
    deploy/lobehub/
    ├── patch_lobehub.py          # thin CLI entry point
    ├── engine.py                 # this file — core types + engine + CLI
    └── patches/                  # auto-discovered patch modules

Each patch module exports:
    meta: PatchMeta               # declarative metadata
    apply(ctx: PatchContext) -> bool  # apply logic; True = applied, False = skipped

Manifest model
--------------
The single source of truth for "which files in lobehub-ui were written by
which patch" is ``lobehub-ui/.lca-manifest.json``. Every ``ctx.write*`` call
records its (patch, rel) pair into the manifest. The old ``.lca-patched``
stamp and ``.lca-patch-hashes`` files are migrated once on first run and
then deleted.

Reconcile semantics
-------------------
``reconcile()`` is the heart of the engine. Behaviour matrix:

    manifest.patches   discover_patches()    action
    ────────────────   ──────────────────    ──────────────────────────────
    absent             has module            create entry, pending apply
    absent             empty (fresh)         cold-start sweep + create entries
    present, sha same  has module            noop (idempotent)
    present, sha diff  has module            restore writes, redo apply
    present            absent or unloadable  orphan → restore writes, remove

``failed_names`` lists patch names whose source file exists in ``patches/``
but failed to import — those are NOT treated as orphans.

Usage:
    python3 deploy/lobehub/patch_lobehub.py              # apply == reconcile + apply
    python3 deploy/lobehub/patch_lobehub.py reconcile     # reconcile only
    python3 deploy/lobehub/patch_lobehub.py verify       # check markers
    python3 deploy/lobehub/patch_lobehub.py list          # show patch set
    python3 deploy/lobehub/patch_lobehub.py drift         # detect unregistered edits
    python3 deploy/lobehub/patch_lobehub.py manifest      # JSON manifest
    python3 deploy/lobehub/patch_lobehub.py doctor        # full health check
    python3 deploy/lobehub/patch_lobehub.py apply <name...>   # specific
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import pkgutil
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "lobehub-ui"
MANIFEST_FILE = UI / ".lca-manifest.json"
LEGACY_STAMP = UI / ".lca-patched"
LEGACY_HASHES = UI / ".lca-patch-hashes"
_UPSTREAM = ROOT / ".lobehub-upstream"

# ── Public types ───────────────────────────────────────────────────────


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
    status: str  # applied | skipped | ok | missing_file | orphan_restored | broken
    detail: str = ""


PatchFunc = Callable[["PatchContext"], bool]


@dataclass
class PatchModule:
    meta: PatchMeta
    apply: PatchFunc


# ── Manifest types ─────────────────────────────────────────────────────


@dataclass
class PatchEntry:
    name: str
    status: str = "skipped"
    source_sha: str = ""
    written: list[str] = field(default_factory=list)


@dataclass
class Manifest:
    schema_version: int = 1
    patched_at: str = ""
    lobehub_release: str = "unknown"
    patches: dict[str, PatchEntry] = field(default_factory=dict)

    def written_files(self) -> set[str]:
        out: set[str] = set()
        for entry in self.patches.values():
            out.update(entry.written)
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "patched_at": self.patched_at,
            "lobehub_release": self.lobehub_release,
            "patches": {
                name: {
                    "status": e.status,
                    "source_sha": e.source_sha,
                    "written": list(e.written),
                }
                for name, e in self.patches.items()
            },
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Manifest:
        m = cls(
            schema_version=int(data.get("schema_version", 1)),
            patched_at=str(data.get("patched_at", "")),
            lobehub_release=str(data.get("lobehub_release", "unknown")),
        )
        raw = data.get("patches") or {}
        if isinstance(raw, dict):
            for name, entry in raw.items():
                if not isinstance(entry, dict):
                    continue
                m.patches[name] = PatchEntry(
                    name=name,
                    status=str(entry.get("status", "skipped")),
                    source_sha=str(entry.get("source_sha", "")),
                    written=[str(r) for r in (entry.get("written") or [])],
                )
        return m


def _read_manifest() -> Manifest:
    if not MANIFEST_FILE.is_file():
        return Manifest()
    try:
        data = json.loads(MANIFEST_FILE.read_text())
    except (json.JSONDecodeError, KeyError):
        return Manifest()
    if not isinstance(data, dict):
        return Manifest()
    return Manifest.from_json(data)


def _write_manifest(m: Manifest) -> None:
    m.patched_at = datetime.now(timezone.utc).isoformat()
    m.lobehub_release = _read_origin_release()
    MANIFEST_FILE.write_text(json.dumps(m.to_json(), indent=2, ensure_ascii=False) + "\n")


def _migrate_legacy_files() -> bool:
    """Migrate legacy .lca-patched + .lca-patch-hashes into the new manifest.

    Returns True if any legacy data was migrated. After migration the
    legacy files are deleted (per the agreed contract).
    """
    if not (LEGACY_STAMP.is_file() or LEGACY_HASHES.is_file()):
        return False

    m = _read_manifest()
    migrated = False

    if LEGACY_HASHES.is_file():
        try:
            raw = json.loads(LEGACY_HASHES.read_text())
            if isinstance(raw, dict):
                for name, sha in raw.items():
                    entry = m.patches.get(name) or PatchEntry(name=str(name))
                    entry.source_sha = str(sha)
                    m.patches[str(name)] = entry
                migrated = True
        except (json.JSONDecodeError, KeyError):
            pass

    if LEGACY_STAMP.is_file():
        try:
            raw = json.loads(LEGACY_STAMP.read_text())
            if isinstance(raw, dict):
                status_map = raw.get("patches")
                if isinstance(status_map, dict):
                    for name, status in status_map.items():
                        entry = m.patches.get(name) or PatchEntry(name=str(name))
                        entry.status = str(status)
                        m.patches[str(name)] = entry
                    migrated = True
        except (json.JSONDecodeError, KeyError):
            pass

    if migrated:
        _write_manifest(m)

    for legacy in (LEGACY_STAMP, LEGACY_HASHES):
        if legacy.is_file():
            legacy.unlink()

    return migrated


# ── PatchContext ───────────────────────────────────────────────────────


class PatchContext:
    """Provides file I/O and string manipulation helpers for patch modules.

    Every successful ``write`` / ``write_if_changed`` / ``create_file`` call
    records (current_patch, rel) into the manifest so the engine can later
    reconcile orphan writes.
    """

    def __init__(
        self,
        ui_dir: Path = UI,
        manifest: Manifest | None = None,
    ) -> None:
        self._ui = ui_dir
        self._manifest = manifest if manifest is not None else Manifest()
        self._current_patch: str = ""

    def _record(self, rel: str) -> None:
        if not self._current_patch:
            return  # writes outside a patch invocation are not owned
        entry = self._manifest.patches.get(self._current_patch)
        if entry is None:
            entry = PatchEntry(name=self._current_patch)
            self._manifest.patches[self._current_patch] = entry
        if rel not in entry.written:
            entry.written.append(rel)

    # ── I/O ────────────────────────────────────────────────────────

    def path(self, rel: str) -> Path:
        return self._ui / rel

    def read(self, rel: str) -> str:
        p = self.path(rel)
        if not p.is_file():
            raise FileNotFoundError(f"missing {p} — run ./scripts/sync_lobehub_ui.sh first")
        return p.read_text()

    def write(self, rel: str, text: str) -> None:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self._record(rel)

    def write_if_changed(self, rel: str, text: str) -> bool:
        """Write file only when content differs. Returns True if written."""
        p = self.path(rel)
        try:
            current = p.read_text()
        except FileNotFoundError:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            self._record(rel)
            return True
        if current != text:
            p.write_text(text)
            self._record(rel)
            return True
        return False

    def has_marker(self, rel: str, marker: str) -> bool:
        try:
            return marker in self.read(rel)
        except FileNotFoundError:
            return False

    def replace_once(self, rel: str, anchor: str, insert: str, *, label: str = "") -> str:
        text = self.read(rel)
        if anchor not in text:
            tag = label or rel
            raise SystemExit(f"[{tag}] anchor not found")
        return text.replace(anchor, insert, 1)

    def replace_first_of(
        self,
        rel: str,
        replacements: tuple[tuple[str, str], ...],
        *,
        label: str,
    ) -> str:
        text = self.read(rel)
        for anchor, insert in replacements:
            if anchor in text:
                return text.replace(anchor, insert, 1)
        needles = " | ".join(repr(a[:80]) for a, _ in replacements)
        raise SystemExit(f"[{label}] none of {len(replacements)} anchors found: {needles}")

    def replace_all(self, rel: str, old: str, new: str) -> str:
        text = self.read(rel)
        return text.replace(old, new)

    def create_file(self, rel: str, content: str) -> bool:
        p = self.path(rel)
        if p.is_file():
            return False
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self._record(rel)
        return True


# ── Discovery ──────────────────────────────────────────────────────────


def discover_patches() -> list[PatchModule]:
    """Scan patches/ directory, import modules, collect PatchMeta + apply."""
    import deploy.lobehub.patches as patches_pkg

    modules: list[PatchModule] = []
    pkg_path = patches_pkg.__path__

    for _importer, modname, _ispkg in pkgutil.walk_packages(
        pkg_path, prefix="deploy.lobehub.patches."
    ):
        if modname.endswith(".__init__"):
            continue
        try:
            mod = importlib.import_module(modname)
        except Exception as exc:
            print(
                f"[discovery] WARNING: failed to import {modname}: {exc}",
                file=sys.stderr,
            )
            continue

        meta = getattr(mod, "meta", None)
        apply_fn = getattr(mod, "apply", None)
        if meta is None or apply_fn is None:
            continue
        if not isinstance(meta, PatchMeta):
            print(
                f"[discovery] WARNING: {modname}.meta is not PatchMeta",
                file=sys.stderr,
            )
            continue
        modules.append(PatchModule(meta=meta, apply=apply_fn))

    return modules


def discover_patches_with_failures() -> tuple[list[PatchModule], list[str]]:
    """Like ``discover_patches`` but also returns names of patches whose
    source file exists yet failed to import — must NOT be treated as
    orphans by reconcile."""
    import deploy.lobehub.patches as patches_pkg

    modules: list[PatchModule] = []
    failed: list[str] = []
    pkg_path = patches_pkg.__path__

    name_re = re.compile(r'^\s*name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)

    for _importer, modname, _ispkg in pkgutil.walk_packages(
        pkg_path, prefix="deploy.lobehub.patches."
    ):
        if modname.endswith(".__init__"):
            continue
        try:
            mod = importlib.import_module(modname)
        except Exception as exc:
            print(
                f"[discovery] WARNING: failed to import {modname}: {exc}",
                file=sys.stderr,
            )
            # Recover patch name from source so reconcile doesn't mistake
            # an unloadable patch for an orphan.
            try:
                source_path = Path(modname.replace(".", "/") + ".py")
                text = source_path.read_text(encoding="utf-8")
                m = name_re.search(text)
                failed.append(m.group(1) if m else modname.rsplit(".", 1)[-1])
            except OSError:
                failed.append(modname.rsplit(".", 1)[-1])
            continue

        meta = getattr(mod, "meta", None)
        apply_fn = getattr(mod, "apply", None)
        if meta is None or apply_fn is None:
            continue
        if not isinstance(meta, PatchMeta):
            continue
        modules.append(PatchModule(meta=meta, apply=apply_fn))

    return modules, failed


# ── Engine helpers ─────────────────────────────────────────────────────


def _filter(modules: list[PatchModule], names: tuple[str, ...]) -> list[PatchModule]:
    if not names:
        return list(modules)
    by_name = {m.meta.name: m for m in modules}
    selected: list[PatchModule] = []
    for n in names:
        if n not in by_name:
            available = ", ".join(sorted(by_name))
            raise SystemExit(f"unknown patch: {n}\nAvailable: {available}")
        selected.append(by_name[n])
    return selected


def _compute_patch_hash(pm: PatchModule) -> str:
    """SHA-256 of the patch module's source file."""
    source_path = Path(inspect.getfile(pm.apply))
    return hashlib.sha256(source_path.read_bytes()).hexdigest()


def _restore_from_upstream(rels: list[str]) -> int:
    """Restore target files from upstream cache. Returns count restored."""
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


# ── Reconcile (single source of truth) ────────────────────────────────


def reconcile(
    modules: list[PatchModule] | None = None,
    failed_names: list[str] | None = None,
) -> list[PatchResult]:
    """Reconcile lobehub-ui with the current patch set.

    Behaviour matrix (single source of truth — the manifest):

    ┌─────────────────────┬────────────────────────┬──────────────────────┐
    │ manifest.patches    │ discover_patches()     │ action               │
    ├─────────────────────┼────────────────────────┼──────────────────────┤
    │ absent              │ has module             │ create entry         │
    │ absent              │ empty (fresh)          │ cold-start sweep     │
    │ present, sha same   │ has module             │ noop                 │
    │ present, sha changed│ has module             │ restore + re-apply   │
    │ present             │ absent or unloadable    │ orphan → restore     │
    └─────────────────────┴────────────────────────┴──────────────────────┘

    ``failed_names`` lists patch names whose source file exists in
    ``patches/`` but failed to import — those are NOT treated as orphans.
    """
    _migrate_legacy_files()
    if modules is None:
        modules, _failed = discover_patches_with_failures()
    manifest = _read_manifest()
    results: list[PatchResult] = []
    failed_set = set(failed_names or [])
    current_names = {pm.meta.name for pm in modules} | failed_set

    # ── 0. Cold-start orphan sweep ──────────────────────────────────
    if not manifest.patches:
        declared: set[str] = set()
        for pm in modules:
            declared.update(pm.meta.files)
        rels_to_restore: list[str] = []
        if UI.is_dir() and _UPSTREAM.is_dir():
            for path in UI.rglob("*"):
                if not path.is_file():
                    continue
                rel = str(path.relative_to(UI))
                if _is_ignored(rel):
                    continue
                if rel in declared:
                    continue
                upstream_path = _UPSTREAM / rel
                if not upstream_path.is_file():
                    continue
                try:
                    if path.read_bytes() == upstream_path.read_bytes():
                        continue
                except OSError:
                    continue
                rels_to_restore.append(rel)
        if rels_to_restore:
            count = _restore_from_upstream(sorted(set(rels_to_restore)))
            results.append(
                PatchResult(
                    "<cold-start orphan sweep>",
                    "orphan_restored",
                    f"{count} divergent file(s) restored from upstream",
                )
            )

    # ── 1. Orphans: in manifest, not in current ─────────────────────
    orphan_names = [name for name in manifest.patches if name not in current_names]
    for name in orphan_names:
        entry = manifest.patches.pop(name)
        if entry.written:
            restored = _restore_from_upstream(entry.written)
            results.append(
                PatchResult(
                    name,
                    "orphan_restored",
                    f"{restored} files restored from upstream",
                )
            )
        else:
            results.append(PatchResult(name, "orphan_restored", "no recorded writes (legacy)"))

    # ── 2. Stale source + cold-start declared divergence ───────────
    cold_start = not manifest.patches
    for pm in modules:
        sha = _compute_patch_hash(pm)
        existing = manifest.patches.get(pm.meta.name)
        sha_changed = (
            existing is not None and existing.source_sha != "" and existing.source_sha != sha
        )
        declared_diverges: list[str] = []
        if cold_start and existing is None:
            for rel in pm.meta.files:
                disk = UI / rel
                upstream = _UPSTREAM / rel
                if disk.is_file() and upstream.is_file():
                    try:
                        if disk.read_bytes() != upstream.read_bytes():
                            declared_diverges.append(rel)
                    except OSError:
                        pass

        if sha_changed or declared_diverges:
            to_restore: set[str] = set()
            if existing is not None:
                to_restore.update(existing.written)
            to_restore.update(declared_diverges)
            if to_restore:
                _restore_from_upstream(sorted(to_restore))
            if existing is None:
                manifest.patches[pm.meta.name] = PatchEntry(
                    name=pm.meta.name, source_sha=sha, status="pending"
                )
            else:
                existing.written = []
                existing.source_sha = sha
                existing.status = "pending"
        elif existing is None:
            manifest.patches[pm.meta.name] = PatchEntry(
                name=pm.meta.name, source_sha=sha, status="pending"
            )

    # Persist reconcile changes (orphan removals, sha updates).
    if results:
        _write_manifest(manifest)

    return results


# ── Apply ──────────────────────────────────────────────────────────────


def apply_patches(names: tuple[str, ...] = ()) -> list[PatchResult]:
    """Apply all (or named) patches idempotently.

    Equivalent to ``reconcile()`` followed by applying each selected patch.
    """
    if not UI.is_dir():
        print("[patch] skip: lobehub-ui/ missing", file=sys.stderr)
        sys.exit(0)

    modules = discover_patches()
    selected = _filter(modules, names)
    _, failed = discover_patches_with_failures()
    reconcile(modules, failed_names=failed)

    manifest = _read_manifest()
    results: list[PatchResult] = []
    applied_count = 0
    ctx = PatchContext(manifest=manifest)

    for pm in selected:
        ctx._current_patch = pm.meta.name
        try:
            was_applied = pm.apply(ctx)
        except SystemExit as exc:
            results.append(PatchResult(pm.meta.name, "broken", str(exc)))
            _log("BROKEN", pm.meta.name, str(exc))
            ctx._current_patch = ""
            continue
        ctx._current_patch = ""

        status = "applied" if was_applied else "skipped"
        if was_applied:
            applied_count += 1
        entry = manifest.patches.get(pm.meta.name) or PatchEntry(name=pm.meta.name)
        entry.status = status
        entry.source_sha = _compute_patch_hash(pm)
        manifest.patches[pm.meta.name] = entry
        results.append(PatchResult(pm.meta.name, status))
        _log(status.upper(), pm.meta.name)

    _write_manifest(manifest)
    print(f"\n[patch] done: {applied_count} applied, {len(results) - applied_count} skipped")
    return results


# ── Verify ─────────────────────────────────────────────────────────────


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
    print("Commands: apply | reconcile | verify | list [--verbose] | drift | manifest | doctor")


# ── Drift Guard ────────────────────────────────────────────────────────

_DRIFT_IGNORE = frozenset(
    {
        ".env",
        ".lca-manifest.json",
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

    _migrate_legacy_files()
    manifest = _read_manifest()
    covered = manifest.written_files()
    modules, failed = discover_patches_with_failures()
    declared_names = {pm.meta.name for pm in modules} | set(failed)
    declared_files = {f for pm in modules for f in pm.meta.files}
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
            owner_hint = ""
            if rel in declared_files:
                owner_hint = " [declared in meta.files but never recorded as applied]"
            violations.append(f"MODIFIED (not in any patch): {rel}{owner_hint}")

    # Manifest self-consistency
    for name, entry in manifest.patches.items():
        if entry.written and name not in declared_names:
            violations.append(
                f"MANIFEST ORPHAN: '{name}' owns {len(entry.written)} file(s) "
                f"but no patch module exists — run reconcile"
            )

    if verbose:
        if violations:
            print(f"\n[drift] ❌ {len(violations)} unregistered modification(s):")
            for v in violations:
                print(f"  • {v}")
            print(
                "\n[drift] FIX: register as a patch in deploy/lobehub/patches/, "
                "or run reconcile if the patch was reverted"
            )
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

    print("\n── 4. Manifest orphans ──")
    _migrate_legacy_files()
    manifest = _read_manifest()
    declared = {pm.meta.name for pm in modules}
    manifest_orphans = [n for n in manifest.patches if n not in declared]
    if manifest_orphans:
        print(
            f"  ❌ {len(manifest_orphans)} patch(es) in manifest but not "
            f"registered: {', '.join(manifest_orphans)}"
        )
        print("     FIX: run reconcile (or apply) — orphans are restored automatically")
        issues += len(manifest_orphans)
    else:
        print("  ✅ no manifest orphans")

    print("\n" + "=" * 60)
    if issues == 0:
        print("  ✅ All checks passed")
    else:
        print(f"  ❌ {issues} issue(s) found")
    print("=" * 60)
    return issues


# ── CLI ────────────────────────────────────────────────────────────────

_COMMANDS = ("apply", "reconcile", "verify", "list", "drift", "manifest", "doctor")


def main() -> None:
    args = sys.argv[1:]
    cmd = "apply"
    names: list[str] = []
    verbose = False

    i = 0
    while i < len(args):
        a = args[i]
        if a in _COMMANDS:
            cmd = a
        elif a in ("--verbose", "-v"):
            verbose = True
        elif a == "--reset":
            # Backwards-compat alias: ``--reset`` used to mean "restore all
            # then re-apply". That is now the default behaviour of ``apply``.
            cmd = "apply"
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
        m = generate_manifest()
        print(json.dumps(m, indent=2, ensure_ascii=False))
    elif cmd == "doctor":
        issue_count = doctor()
        sys.exit(1 if issue_count else 0)
    elif cmd == "reconcile":
        results = reconcile()
        if results:
            for r in results:
                _log(r.status.upper(), r.name, r.detail)
            orphan_count = sum(1 for r in results if r.status == "orphan_restored")
            print(
                f"\n[reconcile] done: {orphan_count} orphan(s) restored, "
                f"{len(results) - orphan_count} entries reconciled"
            )
        else:
            print("[reconcile] ✅ lobehub-ui matches the patch set")
    else:
        results = apply_patches(tuple(names))
        broken_results = [r for r in results if r.status == "broken"]
        sys.exit(1 if broken_results else 0)


# ── Logging ────────────────────────────────────────────────────────────


def _log(status: str, name: str, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    print(f"[patch] {status:<18} {name}{suffix}")


if __name__ == "__main__":
    main()
