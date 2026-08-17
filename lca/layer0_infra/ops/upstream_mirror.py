"""Mirror verification: keep ``lca/packages/`` structurally 1:1 with ``~/deepseek-harness/packages/``.

Why this exists
---------------
``deepseek-harness`` is the upstream reference for package decomposition. We mirror its
directory layout under ``lca/packages/`` so that when upstream adds / moves / renames a
package, we can locate the corresponding LCA module quickly. The CLI command
``lca-ops check-upstream`` (and its ``--sync`` variant) is the operational front of this.

Path conversion rules (forced by Python conventions)
----------------------------------------------------
* Upstream package dirs use hyphens (``llm-deepseek``). Python identifiers cannot have
  hyphens, so we convert them to underscores (``llm_deepseek``). This is the only allowed
  structural deviation from upstream.
* Upstream ``src/<stem>.ts`` → local ``src/<stem>.py``. Stem is preserved verbatim;
  only the extension changes.

Verification levels
-------------------
The comparison walks three levels and reports missing/extra at each:

1. Top-level package names (``acp``, ``api``, ``llm``, ...).
2. Sub-package names within each top-level (``llm/llm-deepseek`` etc.).
3. Source file stems within each sub-package's ``src/`` (``index``, ``assembler`` ...).

README / tests / package.json / tsconfig.json are intentionally NOT mirrored — they are
not part of the source layout we want to track. Tests live under ``tests/`` in our repo;
README can be regenerated from upstream separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Directories we never descend into for either side.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "lib",
        "dist",
        ".git",
        "__pycache__",
        "tests",
        "test",
        "fixtures",
        "examples",
        # DSH's lib/ sometimes contains generated *.d.ts; tests is in our own tests/.
    }
)


def to_python_pkg(name: str) -> str:
    """Convert a hyphenated upstream package name to a Python-valid identifier.

    >>> to_python_pkg("llm-deepseek")
    'llm_deepseek'
    >>> to_python_pkg("session-persistence-jsonl")
    'session_persistence_jsonl'
    """
    return name.replace("-", "_")


def to_python_file(stem: str) -> str:
    """Convert an upstream ``.ts`` stem to a local ``.py`` filename."""
    return f"{stem}.py"


@dataclass(frozen=True)
class PackageInventory:
    """The structural shape of a single sub-package (one nested folder with src/)."""

    # Set of <stem> names that exist in src/ (e.g. {"index", "invariant", "assembler"}).
    src_stems: frozenset[str] = frozenset()

    @property
    def src_count(self) -> int:
        return len(self.src_stems)


@dataclass(frozen=True)
class UpstreamTree:
    """Full inventory of one upstream top-level package."""

    # Set of upstream sub-package names as they appear on disk (e.g. "llm-deepseek").
    sub_names: frozenset[str] = frozenset()
    # sub_name (upstream form, hyphens) → its src/ inventory.
    subs: dict[str, PackageInventory] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalMirror:
    """Full inventory of the local mirror for one top-level package."""

    # Set of local sub-package names (Python form, underscores).
    sub_names: frozenset[str] = frozenset()
    # sub_name (local form) → its src/ inventory.
    subs: dict[str, PackageInventory] = field(default_factory=dict)


@dataclass(frozen=True)
class MirrorDiff:
    """Structural differences between upstream and the local mirror."""

    # Top-level packages that exist upstream but not locally.
    missing_top: tuple[str, ...] = ()
    # Top-level packages that exist locally but not upstream.
    extra_top: tuple[str, ...] = ()
    # (top, upstream_sub) pairs missing locally. The local form is implicit
    # via to_python_pkg().
    missing_sub: tuple[tuple[str, str], ...] = ()
    # (top, local_sub) pairs present locally but absent upstream.
    extra_sub: tuple[tuple[str, str], ...] = ()
    # (top, upstream_sub, stem) triples missing in local src/.
    missing_files: tuple[tuple[str, str, str], ...] = ()
    # (top, local_sub, stem) triples present locally but absent upstream.
    extra_files: tuple[tuple[str, str, str], ...] = ()

    @property
    def total_missing(self) -> int:
        return len(self.missing_top) + len(self.missing_sub) + len(self.missing_files)

    @property
    def total_extra(self) -> int:
        return len(self.extra_top) + len(self.extra_sub) + len(self.extra_files)

    @property
    def is_in_sync(self) -> bool:
        return self.total_missing == 0 and self.total_extra == 0


def _walk_src_stems(src_dir: Path, extension: str) -> frozenset[str]:
    """Return the set of file stems in ``src_dir`` matching the given extension.

    Recurses into subdirs and returns stems with their relative path joined by ``__`` so
    nested files stay distinguishable (e.g. ``client__sessions__manager``). Excludes:

    * ``__init__`` package markers (they are not tracked source).
    * TypeScript declaration files (``*.d.ts`` / ``*.d.tsx``) — those are not source,
      they are type info that maps to typing stubs in Python.

    When matching upstream (``.ts``), the scan uses just ``.ts`` so ``.d.ts`` is naturally
    excluded. When matching local (``.py``), the scan uses ``.py`` only.
    """
    if not src_dir.is_dir():
        return frozenset()
    stems: set[str] = set()
    # rglob("*.ts") matches both .ts and .d.ts; filter out .d.ts here.
    suffixes = (".d.ts", ".d.tsx")
    for path in src_dir.rglob(f"*{extension}"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if any(path.name.endswith(s) for s in suffixes):
            continue
        rel = path.relative_to(src_dir)
        stem = rel.with_suffix("").as_posix().replace("/", "__")
        if stem.endswith("__init__") or stem == "__init__":
            continue
        stems.add(stem)
    return frozenset(stems)


def _inventory_upstream(top_dir: Path) -> UpstreamTree:
    """Walk a single upstream top-level package directory."""
    sub_names: set[str] = set()
    subs: dict[str, PackageInventory] = {}
    for entry in sorted(top_dir.iterdir()):
        if not entry.is_dir() or entry.name in _SKIP_DIRS or entry.name.startswith("."):
            continue
        # Skip files that aren't real npm packages.
        if not (entry / "package.json").exists():
            continue
        sub_names.add(entry.name)
        src_dir = entry / "src"
        stems = _walk_src_stems(src_dir, ".ts")
        subs[entry.name] = PackageInventory(src_stems=stems)
    return UpstreamTree(sub_names=frozenset(sub_names), subs=subs)


def _inventory_local(top_dir: Path) -> LocalMirror:
    """Walk a single local mirror top-level package directory."""
    sub_names: set[str] = set()
    subs: dict[str, PackageInventory] = {}
    if not top_dir.is_dir():
        return LocalMirror()
    for entry in sorted(top_dir.iterdir()):
        if not entry.is_dir() or entry.name in _SKIP_DIRS or entry.name.startswith("."):
            continue
        # Local packages: require __init__.py to count as a real package.
        if not (entry / "__init__.py").exists():
            continue
        sub_names.add(entry.name)
        src_dir = entry / "src"
        stems = _walk_src_stems(src_dir, ".py")
        subs[entry.name] = PackageInventory(src_stems=stems)
    return LocalMirror(sub_names=frozenset(sub_names), subs=subs)


def scan_upstream(upstream_root: Path) -> dict[str, UpstreamTree]:
    """Scan an upstream ``packages/`` root and return ``{top_pkg: UpstreamTree}``.

    Top-level is a namespace folder; sub-packages inside are validated by
    ``_inventory_upstream``. Empty namespaces (no real sub-packages) are dropped.
    """
    if not upstream_root.is_dir():
        raise FileNotFoundError(f"Upstream not found: {upstream_root}")
    trees: dict[str, UpstreamTree] = {}
    for entry in sorted(upstream_root.iterdir()):
        if not entry.is_dir() or entry.name in _SKIP_DIRS or entry.name.startswith("."):
            continue
        tree = _inventory_upstream(entry)
        # Skip namespace folders with no real sub-packages — they're noise.
        if not tree.sub_names:
            continue
        trees[entry.name] = tree
    return trees


def scan_local(target_root: Path) -> dict[str, LocalMirror]:
    """Scan a local ``packages/`` root and return ``{top_pkg: LocalMirror}``.

    Top-level must have ``__init__.py`` at its root (Python convention). Same rule
    applies to sub-packages.
    """
    trees: dict[str, LocalMirror] = {}
    if not target_root.is_dir():
        return trees
    for entry in sorted(target_root.iterdir()):
        if not entry.is_dir() or entry.name in _SKIP_DIRS or entry.name.startswith("."):
            continue
        if not (entry / "__init__.py").exists():
            continue
        trees[entry.name] = _inventory_local(entry)
    return trees


def diff_trees(
    upstream: dict[str, UpstreamTree],
    local: dict[str, LocalMirror],
) -> MirrorDiff:
    """Compute the structural diff between an upstream scan and a local scan.

    Levels walked:
    1. Top-level packages.
    2. Sub-packages under each top-level.
    3. ``src/`` file stems under each sub-package.

    ``extra_*`` covers everything present locally but absent upstream (LCA additions).
    """
    up_tops = set(upstream)
    loc_tops = set(local)
    missing_top = tuple(sorted(up_tops - loc_tops))
    extra_top = tuple(sorted(loc_tops - up_tops))

    missing_sub: list[tuple[str, str]] = []
    extra_sub: list[tuple[str, str]] = []
    missing_files: list[tuple[str, str, str]] = []
    extra_files: list[tuple[str, str, str]] = []

    # When a top is missing locally, ALL its subs are also missing.
    for top in sorted(missing_top):
        for sub in sorted(upstream[top].sub_names):
            missing_sub.append((top, sub))
            for stem in sorted(upstream[top].subs[sub].src_stems):
                missing_files.append((top, sub, stem))

    common_tops = sorted(up_tops & loc_tops)
    for top in common_tops:
        up_tree = upstream[top]
        loc_tree = local[top]

        up_subs_py = {to_python_pkg(s): s for s in up_tree.sub_names}
        loc_subs = set(loc_tree.sub_names)
        up_only_subs = set(up_subs_py) - loc_subs
        loc_only_subs = loc_subs - set(up_subs_py)

        for py_name in sorted(up_only_subs):
            missing_sub.append((top, up_subs_py[py_name]))
        for py_name in sorted(loc_only_subs):
            extra_sub.append((top, py_name))

        for py_name in sorted(set(up_subs_py) & loc_subs):
            up_sub_name = up_subs_py[py_name]
            up_stems = up_tree.subs[up_sub_name].src_stems
            loc_stems = loc_tree.subs[py_name].src_stems
            for stem in sorted(up_stems - loc_stems):
                missing_files.append((top, up_sub_name, stem))
            for stem in sorted(loc_stems - up_stems):
                extra_files.append((top, py_name, stem))

    # Extra tops also have their sub-packages and files tracked as extras.
    for top in sorted(extra_top):
        loc_tree = local[top]
        for sub in sorted(loc_tree.sub_names):
            extra_sub.append((top, sub))
            for stem in sorted(loc_tree.subs[sub].src_stems):
                extra_files.append((top, sub, stem))

    return MirrorDiff(
        missing_top=missing_top,
        extra_top=extra_top,
        missing_sub=tuple(missing_sub),
        extra_sub=tuple(extra_sub),
        missing_files=tuple(missing_files),
        extra_files=tuple(extra_files),
    )


def coverage_stats(
    upstream: dict[str, UpstreamTree],
    diff: MirrorDiff,
) -> dict[str, int]:
    """Compute coverage numbers used by the human-readable report."""
    up_top = len(upstream)
    up_sub = sum(len(t.sub_names) for t in upstream.values())
    up_files = sum(t.subs[s].src_count for t in upstream.values() for s in t.sub_names)
    missing = {
        "top": len(diff.missing_top),
        "sub": len(diff.missing_sub),
        "files": len(diff.missing_files),
    }

    def pct(n: int, d: int) -> float:
        return 100.0 * (d - n) / d if d else 100.0

    return {
        "upstream_top": up_top,
        "upstream_sub": up_sub,
        "upstream_files": up_files,
        "missing_top": missing["top"],
        "missing_sub": missing["sub"],
        "missing_files": missing["files"],
        "top_pct": pct(missing["top"], up_top),
        "sub_pct": pct(missing["sub"], up_sub),
        "files_pct": pct(missing["files"], up_files),
    }


def format_report(
    diff: MirrorDiff,
    stats: dict[str, int],
    *,
    upstream_root: Path,
    target_root: Path,
) -> str:
    """Render a human-readable diff report. Pure text, no ANSI colors."""
    lines: list[str] = []
    lines.append("=== Upstream Mirror Report ===")
    lines.append(f"upstream: {upstream_root}")
    lines.append(f"target:   {target_root}")
    lines.append("")
    lines.append(
        f"upstream: {stats['upstream_top']} top / "
        f"{stats['upstream_sub']} sub / "
        f"{stats['upstream_files']} src files"
    )
    lines.append(
        f"missing:  {stats['missing_top']:>3} top "
        f"({stats['top_pct']:5.1f}% present) | "
        f"{stats['missing_sub']:>3} sub "
        f"({stats['sub_pct']:5.1f}% present) | "
        f"{stats['missing_files']:>5} files "
        f"({stats['files_pct']:5.1f}% present)"
    )
    lines.append("")
    status = "IN SYNC" if diff.is_in_sync else "OUT OF SYNC"
    lines.append(f"status: {status}")
    lines.append("")

    if diff.missing_top:
        lines.append(f"-- missing top-level packages ({len(diff.missing_top)}) --")
        for name in diff.missing_top:
            lines.append(f"  + {name}/")
        lines.append("")
    if diff.missing_sub:
        lines.append(f"-- missing sub-packages ({len(diff.missing_sub)}) --")
        for top, sub in diff.missing_sub:
            lines.append(f"  + {top}/{to_python_pkg(sub)}/  (upstream: {sub})")
        lines.append("")
    if diff.missing_files:
        lines.append(f"-- missing src files ({len(diff.missing_files)}) --")
        # group by top/sub for readability
        by_sub: dict[tuple[str, str], list[str]] = {}
        for top, sub, stem in diff.missing_files:
            by_sub.setdefault((top, sub), []).append(stem)
        for (top, sub), stems in sorted(by_sub.items()):
            lines.append(f"  + {top}/{to_python_pkg(sub)}/src/")
            for stem in stems:
                lines.append(f"      - {stem}.py")
        lines.append("")

    if diff.extra_top:
        lines.append(f"-- extra top-level (local only) ({len(diff.extra_top)}) --")
        for name in diff.extra_top:
            lines.append(f"  - {name}/")
        lines.append("")
    if diff.extra_sub:
        lines.append(f"-- extra sub-packages (local only) ({len(diff.extra_sub)}) --")
        for top, sub in diff.extra_sub:
            lines.append(f"  - {top}/{sub}/")
        lines.append("")
    if diff.extra_files:
        lines.append(f"-- extra src files (local only) ({len(diff.extra_files)}) --")
        by_sub = {}
        for top, sub, stem in diff.extra_files:
            by_sub.setdefault((top, sub), []).append(stem)
        for (top, sub), stems in sorted(by_sub.items()):
            lines.append(f"  - {top}/{sub}/src/")
            for stem in stems:
                lines.append(f"      + {stem}.py")
        lines.append("")

    if not diff.total_missing and not diff.total_extra:
        lines.append("nothing to sync.")
    return "\n".join(lines)


def format_json(
    diff: MirrorDiff,
    stats: dict[str, int],
    *,
    upstream_root: Path,
    target_root: Path,
) -> str:
    """Render a JSON report for CI consumption."""
    import json

    payload = {
        "upstream": str(upstream_root),
        "target": str(target_root),
        "in_sync": diff.is_in_sync,
        "stats": stats,
        "missing": {
            "top": list(diff.missing_top),
            "sub": [
                {"top": t, "upstream_sub": s, "local_sub": to_python_pkg(s)}
                for t, s in diff.missing_sub
            ],
            "files": [
                {"top": t, "sub": to_python_pkg(s), "stem": st} for t, s, st in diff.missing_files
            ],
        },
        "extra": {
            "top": list(diff.extra_top),
            "sub": [{"top": t, "sub": s} for t, s in diff.extra_sub],
            "files": [{"top": t, "sub": s, "stem": st} for t, s, st in diff.extra_files],
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Sync: generate missing skeleton files. Idempotent — never overwrites.
# ---------------------------------------------------------------------------

_PY_STUB = '''"""TODO: port from upstream deepseek-harness.

Upstream source:
  package : {top}/{sub}
  src ts  : {ts_rel}

Skeleton created by ``lca-ops check-upstream --sync``. Replace this stub with the
Python equivalent. Do not edit this header — it is regenerated when upstream
changes are merged.
"""
'''


def _stub_for_file(top: str, sub: str, stem: str) -> str:
    ts_rel = f"{top}/{sub}/src/{stem}.ts"
    return _PY_STUB.format(top=top, sub=sub, ts_rel=ts_rel)


def _ensure_top_init(top_dir: Path, top: str, *, force: bool) -> bool:
    """Ensure ``top_dir/__init__.py`` exists. Return True if we wrote it."""
    init = top_dir / "__init__.py"
    if init.exists() and not force:
        return False
    init.write_text(
        f'"""Top-level package mirror of upstream deepseek-harness ``{top}/``."""\n',
        encoding="utf-8",
    )
    return True


def _ensure_src_init(src_dir: Path, top: str, sub: str, *, force: bool) -> bool:
    """Ensure ``src_dir/__init__.py`` exists. Return True if we wrote it."""
    init = src_dir / "__init__.py"
    if init.exists() and not force:
        return False
    init.write_text(f'"""Mirrors ``{top}/{sub}/src/``."""\n', encoding="utf-8")
    return True


def sync_skeletons(
    upstream_root: Path,
    target_root: Path,
    diff: MirrorDiff,
    *,
    force: bool = False,
) -> tuple[int, int, int]:
    """Generate missing skeleton files in ``target_root``.

    Returns ``(created_top, created_sub, created_files)``. ``created_top`` counts any
    top-level ``__init__.py`` that this call wrote (whether the diff listed it in
    ``missing_top`` or we had to create the parent for a missing sub-package).
    Existing files are NOT overwritten unless ``force=True``.
    """
    created_top = created_sub = created_files = 0

    # 1. Top-level packages explicitly missing.
    for top in diff.missing_top:
        d = target_root / top
        d.mkdir(parents=True, exist_ok=True)
        if _ensure_top_init(d, top, force=force):
            created_top += 1

    # 2. Sub-packages. Their parent top may not yet have __init__.py.
    by_top: dict[str, list[str]] = {}
    for top, sub in diff.missing_sub:
        by_top.setdefault(top, []).append(sub)

    files_by_top_sub: dict[tuple[str, str], list[str]] = {}
    for top, sub, stem in diff.missing_files:
        files_by_top_sub.setdefault((top, sub), []).append(stem)

    for top, subs in by_top.items():
        top_dir = target_root / top
        top_dir.mkdir(parents=True, exist_ok=True)
        if _ensure_top_init(top_dir, top, force=force):
            created_top += 1
        for sub in subs:
            local_name = to_python_pkg(sub)
            sub_dir = top_dir / local_name
            if sub_dir.exists() and not force:
                continue
            sub_dir.mkdir(parents=True, exist_ok=True)
            (sub_dir / "__init__.py").write_text(
                f'"""Mirror of upstream deepseek-harness ``{top}/{sub}/``."""\n',
                encoding="utf-8",
            )
            (sub_dir / "src").mkdir(exist_ok=True)
            if _ensure_src_init(sub_dir / "src", top, sub, force=force):
                pass  # counted under created_top via src/__init__.py only if explicit
            created_sub += 1

    # 3. Missing files inside existing sub-packages.
    for (top, sub), stems in files_by_top_sub.items():
        local_name = to_python_pkg(sub)
        src_dir = target_root / top / local_name / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        _ensure_src_init(src_dir, top, sub, force=force)
        for stem in stems:
            # Stem is the file name without extension. Reverse the ``__`` flattening
            # to reconstruct the nested path, then append ``.py`` (Python extension).
            # We do NOT use ``Path.with_suffix`` here — it strips only one suffix and
            # would mangle multi-dot stems like ``agent-presets.schema``.
            rel_path = Path(*stem.split("__"))
            target_file = src_dir / rel_path.with_name(rel_path.name + ".py")
            if target_file.exists() and not force:
                continue
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(_stub_for_file(top, sub, stem), encoding="utf-8")
            created_files += 1

    return created_top, created_sub, created_files


def cli_run(
    *,
    upstream: Path,
    target: Path,
    sync: bool,
    force: bool,
    json_output: bool,
) -> int:
    """Entry point used by the typer command. ``0`` = in sync (or synced), ``1`` = out of sync."""
    upstream_trees = scan_upstream(upstream)
    local_trees = scan_local(target)
    diff = diff_trees(upstream_trees, local_trees)
    stats = coverage_stats(upstream_trees, diff)

    if sync:
        created_top, created_sub, created_files = sync_skeletons(
            upstream, target, diff, force=force
        )
        # Re-scan after sync.
        upstream_trees = scan_upstream(upstream)
        local_trees = scan_local(target)
        diff = diff_trees(upstream_trees, local_trees)
        stats = coverage_stats(upstream_trees, diff)
        if json_output:
            payload = {
                "created": {
                    "top": created_top,
                    "sub": created_sub,
                    "files": created_files,
                    "force": force,
                },
                "after_sync": {
                    "in_sync": diff.is_in_sync,
                    "stats": stats,
                },
            }
            print(__import__("json").dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(
                f"sync: created {created_top} top, "
                f"{created_sub} sub, {created_files} files "
                f"(force={force})"
            )
            print(format_report(diff, stats, upstream_root=upstream, target_root=target))
        return 0 if diff.is_in_sync else 1

    if json_output:
        print(format_json(diff, stats, upstream_root=upstream, target_root=target))
    else:
        print(format_report(diff, stats, upstream_root=upstream, target_root=target))
    return 0 if diff.is_in_sync else 1
