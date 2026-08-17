#!/usr/bin/env python3
"""Surface parity check between upstream ``deepseek-harness/packages`` and the local Python mirror.

Walks every ``.ts`` source file under upstream, extracts the public exports (name + kind),
then walks the corresponding ``.py`` module under the local mirror and asserts each
exported name is defined with a compatible kind. Catches:

* Missing local module
* Missing local symbol
* Kind mismatch (e.g. upstream ``function`` but local only declares a ``type`` alias)

The script does NOT verify behavioural equivalence — that is covered by the per-file
test suite at ``tests/packages/``. It only verifies the *public surface* matches, so
LLM-assisted porting has a tight, objective feedback loop: until the surface matches,
do not bother writing tests.

Usage:
    uv run python3 scripts/check_port_surface.py
    uv run python3 scripts/check_port_surface.py --json
    uv run python3 scripts/check_port_surface.py --upstream ~/deepseek-harness/packages \\
        --target lca/packages
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Directories we never descend into for either side.
_SKIP_DIRS: frozenset[str] = frozenset(
    {"node_modules", "lib", "dist", ".git", "__pycache__", "tests", "fixtures"}
)

# --- TypeScript export extraction (regex-based, robust to minor syntax) --------

# Match an exported declaration line. Captures the leading ``export`` modifier plus
# a declaration token. We capture only the FIRST declaration on the line for ``export ...``
# patterns because multi-decl lines are very rare in DSH.
_TS_EXPORT_RE = re.compile(
    r"""^export\s+
        (?:async\s+)?
        (?P<kind>(?:abstract\s+)?class|function|const|let|var|enum|namespace|interface|type)\s+
        (?P<name>[A-Za-z_$][A-Za-z0-9_$]*)
    """,
    re.VERBOSE | re.MULTILINE,
)

# ``export default <ident>`` line.
_TS_EXPORT_DEFAULT_RE = re.compile(
    r"""^export\s+default\s+(?:async\s+)?(?:(?P<kind>class|function)\s+)?(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)""",
    re.VERBOSE | re.MULTILINE,
)

# ``export { a, b as c, type X, ... } from '...'`` (re-export specifier list).
_TS_EXPORT_FROM_RE = re.compile(
    r"""^export\s+(?:type\s+)?\{(?P<body>[^}]+)\}\s*(?:from\s+['"][^'"]+['"])?""",
    re.MULTILINE,
)

# Bare ``export { a, b, type }`` (no from) — a re-binding to an existing local symbol.
_TS_EXPORT_LOCAL_RE = re.compile(
    r"""^export\s+(?:type\s+)?\{(?P<body>[^}]+)\}\s*;""",
    re.MULTILINE,
)

# ``export type X = ...`` — the TS_EXPORT_RE above already matches ``type`` so this is redundant.

# ``export * from '...'`` and ``export type * from '...'``.
_TS_EXPORT_STAR_RE = re.compile(
    r"""^export\s+(?P<typekw>type\s+)?\*\s*(?:as\s+(?P<alias>[A-Za-z_$][A-Za-z0-9_$]*)\s+)?from\s+['"][^'"]+['"]""",
    re.VERBOSE | re.MULTILINE,
)


@dataclass(frozen=True)
class TsExport:
    """One exported symbol extracted from a TypeScript source file."""

    name: str
    kind: str  # "function" | "class" | "const" | "interface" | "type" | "enum" | "default" | "reexport"


@dataclass(frozen=True)
class TsFile:
    """The export surface of one TypeScript source file."""

    relpath: str
    exports: tuple[TsExport, ...]


def extract_ts_exports(path: Path) -> TsFile:
    """Read a .ts file and return its public exports.

    Drops .d.ts declaration files — they are not source.
    """
    if path.suffix != ".ts":
        return TsFile(str(path), ())
    text = path.read_text(encoding="utf-8", errors="replace")
    found: dict[str, TsExport] = {}

    for m in _TS_EXPORT_RE.finditer(text):
        name = m.group("name")
        kind = m.group("kind")
        # ``export abstract class X`` → kind="class" after capture; normalize.
        if kind == "abstract class":
            kind = "class"
        # ``export type X = ...`` and ``export interface X { ... }`` both surface
        # as ``type`` / ``interface`` to consumers — record them as such.
        found.setdefault(name, TsExport(name=name, kind=kind))

    for m in _TS_EXPORT_DEFAULT_RE.finditer(text):
        name = m.group("name")
        explicit_kind = m.group("kind")
        if explicit_kind:
            found.setdefault(name, TsExport(name=name, kind=explicit_kind))
        else:
            # If we already know this name's kind from a prior declaration, keep it.
            if name not in found:
                found[name] = TsExport(name=name, kind="class")

    for m in _TS_EXPORT_FROM_RE.finditer(text):
        body = m.group("body")
        for raw in body.split(","):
            spec = raw.strip()
            if not spec:
                continue
            # ``type X`` or ``type X as Y`` — type-only re-export.
            is_type = spec.startswith("type ")
            spec = spec.removeprefix("type ").strip()
            # ``X as Y`` — exported under Y.
            if " as " in spec:
                _, exported = (s.strip() for s in spec.split(" as ", 1))
            else:
                exported = spec
            if not exported:
                continue
            kind = "type" if is_type else "reexport"
            found.setdefault(exported, TsExport(name=exported, kind=kind))

    for m in _TS_EXPORT_LOCAL_RE.finditer(text):
        body = m.group("body")
        for raw in body.split(","):
            spec = raw.strip()
            if not spec:
                continue
            is_type = spec.startswith("type ")
            spec = spec.removeprefix("type ").strip()
            if " as " in spec:
                _, exported = (s.strip() for s in spec.split(" as ", 1))
            else:
                exported = spec
            if not exported:
                continue
            kind = "type" if is_type else "reexport"
            found.setdefault(exported, TsExport(name=exported, kind=kind))

    for m in _TS_EXPORT_STAR_RE.finditer(text):
        alias = m.group("alias")
        if alias:
            found.setdefault(alias, TsExport(name=alias, kind="reexport"))

    exports = tuple(sorted(found.values(), key=lambda e: e.name))
    return TsFile(relpath=str(path), exports=exports)


# --- Python module surface extraction -----------------------------------------


@dataclass(frozen=True)
class PySymbol:
    """One module-level definition in a Python mirror file."""

    name: str
    kind: str  # "function" | "class" | "constant" | "type"


def extract_py_symbols(path: Path) -> tuple[PySymbol, ...]:
    """Read a .py file and return its module-level public symbols.

    Uses ``ast`` so we don't have to lex Python by hand. Skips private names
    (leading underscore). Symbols defined inside other symbols are NOT exported
    in Python — only module-level definitions count.

    If the module declares ``__all__``, that list is treated as authoritative
    (standard Python idiom): every name in ``__all__`` becomes a public symbol
    whose kind is inferred from its binding (``def``/``class``/assignment).
    Names defined in the module but NOT in ``__all__`` are excluded.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return ()

    # First pass: collect every module-level public binding (name → kind).
    bindings: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                bindings[node.name] = "function"
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                bindings[node.name] = "class"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    bindings.setdefault(target.id, "constant")
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and not node.target.id.startswith("_")
            ):
                kind = "type" if _looks_like_type_alias(node) else "constant"
                bindings[target_id(node)] = kind
        elif isinstance(node, ast.TypeAlias) and not node.name.id.startswith("_"):  # py3.12+
            bindings[node.name.id] = "type"

    # If ``__all__`` is declared, use it as the authoritative export list.
    explicit: list[str] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__" and isinstance(
                    node.value, (ast.List, ast.Tuple)
                ):
                    explicit = [
                        elt.value
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
    if explicit is not None:
        result: list[PySymbol] = []
        for name in explicit:
            kind = bindings.get(name, "constant")
            result.append(PySymbol(name=name, kind=kind))
        return tuple(result)

    return tuple(PySymbol(name=n, kind=k) for n, k in sorted(bindings.items()))


def target_id(node: ast.AnnAssign) -> str:
    """Return the name of an ``AnnAssign`` target (helper for type clarity)."""
    assert isinstance(node.target, ast.Name)
    return node.target.id


def _looks_like_type_alias(node: ast.AnnAssign) -> bool:
    """Heuristic: is this annotated assignment a type alias?

    Detects ``Foo: SomeProtocol[Bar] = ...`` and ``Foo = SomeType`` by checking
    that the annotation looks like a class reference rather than a runtime
    expression. Conservative — false negatives are fine.
    """
    return isinstance(node.annotation, (ast.Name, ast.Attribute, ast.Subscript, ast.BinOp))


# --- Directory walking --------------------------------------------------------


def _walk_ts_files(root: Path) -> dict[str, TsFile]:
    """Walk upstream and return ``{relpath_under_packages/<top>/<sub>/src/<stem>: TsFile}``.

    The key uses forward slashes for portability.
    """
    out: dict[str, TsFile] = {}
    for top in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for sub in sorted(
            p for p in top.iterdir() if p.is_dir() and not p.name.startswith(".")
        ):
            src = sub / "src"
            if not src.is_dir():
                continue
            for ts in sorted(src.rglob("*.ts")):
                if any(part in _SKIP_DIRS for part in ts.parts):
                    continue
                rel = ts.relative_to(root).as_posix()  # <top>/<sub>/src/<stem>.ts
                if ts.name.endswith(".d.ts"):
                    continue
                out[rel] = extract_ts_exports(ts)
    return out


def _walk_py_files(root: Path) -> dict[str, tuple[PySymbol, ...]]:
    """Walk local mirror and return ``{relpath_under_packages/<top>/<sub>/src/<stem>.py: symbols}``."""
    out: dict[str, tuple[PySymbol, ...]] = {}
    if not root.is_dir():
        return out
    for top in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for sub in sorted(
            p for p in top.iterdir() if p.is_dir() and not p.name.startswith(".")
        ):
            src = sub / "src"
            if not src.is_dir():
                continue
            for py in sorted(src.rglob("*.py")):
                if any(part in _SKIP_DIRS for part in py.parts):
                    continue
                if py.name == "__init__.py":
                    continue
                rel = py.relative_to(root).as_posix()
                out[rel] = extract_py_symbols(py)
    return out


# --- Comparison ---------------------------------------------------------------


@dataclass(frozen=True)
class SurfaceDiff:
    """Surface-parity difference between upstream .ts and local .py for one file."""

    relpath: str
    missing_module: bool = False
    extra_ts_exports: tuple[TsExport, ...] = ()
    missing_ts_exports: tuple[TsExport, ...] = ()
    kind_mismatches: tuple[tuple[TsExport, str], ...] = ()


def _ts_to_py_relpath(ts_rel: str) -> str:
    """Convert upstream ``<top>/<sub>/src/[nested/]<stem>.ts`` to its local mirror path.

    The sub-package name is hyphenated upstream and underscored locally (Python
    identifier rule), so we apply the same conversion ``upstream_mirror`` uses.
    Nested src/ subdirectories are preserved verbatim.
    """
    parts = ts_rel.split("/")
    if len(parts) < 4:
        return ts_rel
    top, sub, src_dir, *rest = parts
    sub_py = sub.replace("-", "_")
    # ``rest`` is everything after ``<top>/<sub>/src/``. The last element carries
    # the .ts extension; everything in between is a nested src/ subdirectory.
    if not rest:
        return ts_rel
    last = rest[-1]
    stem, _ext = last.rsplit(".", 1) if "." in last else (last, "")
    if len(rest) > 1:
        nested = "/".join(rest[:-1])
        new_rel = f"{top}/{sub_py}/{src_dir}/{nested}/{stem}.py"
    else:
        new_rel = f"{top}/{sub_py}/{src_dir}/{stem}.py"
    return new_rel


# Map TS kind → expected Python kind (loose — Python doesn't distinguish type/interface).
_TS_TO_PY_KIND = {
    "function": {"function"},
    "class": {"class"},
    "const": {"constant", "function", "class"},  # const could be a callable or constant
    "interface": {"class"},  # Protocol/dataclass
    "type": {"type", "class"},  # NewType/Protocol/dataclass
    "enum": {"class", "constant"},  # IntEnum / StrEnum / constant
    "default": {"class", "function", "constant"},
    "reexport": {"function", "class", "constant", "type"},
}


def _check_one(
    ts_rel: str,
    ts_file: TsFile,
    py_symbols_by_rel: dict[str, tuple[PySymbol, ...]],
) -> SurfaceDiff:
    py_rel = _ts_to_py_relpath(ts_rel)
    if py_rel not in py_symbols_by_rel:
        return SurfaceDiff(relpath=ts_rel, missing_module=True)
    py_names = {s.name: s for s in py_symbols_by_rel[py_rel]}
    extra: list[TsExport] = []
    missing: list[TsExport] = []
    mismatches: list[tuple[TsExport, str]] = []
    for ts_exp in ts_file.exports:
        if ts_exp.name not in py_names:
            # The type-only ``export type *`` is a wildcard — we can't enumerate
            # what it imports without parsing the target file, so we mark it as
            # missing by name and let the user satisfy it with a stub.
            missing.append(ts_exp)
            continue
        py_sym = py_names[ts_exp.name]
        allowed = _TS_TO_PY_KIND.get(ts_exp.kind, {ts_exp.kind})
        if py_sym.kind not in allowed:
            mismatches.append((ts_exp, py_sym.kind))
    return SurfaceDiff(
        relpath=ts_rel,
        extra_ts_exports=tuple(extra),
        missing_ts_exports=tuple(missing),
        kind_mismatches=tuple(mismatches),
    )


def compare(
    upstream_root: Path,
    target_root: Path,
) -> tuple[dict[str, TsFile], list[SurfaceDiff]]:
    """Compare the two trees and return the upstream scan + a list of per-file diffs."""
    ts_files = _walk_ts_files(upstream_root)
    py_symbols = _walk_py_files(target_root)
    diffs: list[SurfaceDiff] = []
    for ts_rel, ts_file in sorted(ts_files.items()):
        diff = _check_one(ts_rel, ts_file, py_symbols)
        if (
            diff.missing_module
            or diff.extra_ts_exports
            or diff.missing_ts_exports
            or diff.kind_mismatches
        ):
            diffs.append(diff)
    return ts_files, diffs


# --- Output formatting --------------------------------------------------------


def _format_text(
    ts_files: dict[str, TsFile],
    diffs: list[SurfaceDiff],
    *,
    upstream_root: Path,
    target_root: Path,
) -> str:
    lines: list[str] = []
    lines.append("=== Port Surface Report ===")
    lines.append(f"upstream: {upstream_root}")
    lines.append(f"target:   {target_root}")
    n_ts = sum(len(f.exports) for f in ts_files.values())
    lines.append(f"upstream: {len(ts_files)} files / {n_ts} exports")
    lines.append(f"files out of parity: {len(diffs)}")
    lines.append("")
    if not diffs:
        lines.append("IN SURFACE SYNC")
        return "\n".join(lines)
    lines.append("OUT OF SURFACE SYNC")
    lines.append("")
    by_top: dict[str, list[SurfaceDiff]] = {}
    for d in diffs:
        top = d.relpath.split("/", 1)[0]
        by_top.setdefault(top, []).append(d)
    for top, ds in sorted(by_top.items()):
        lines.append(f"## {top} ({len(ds)} files out of parity)")
        for d in ds:
            if d.missing_module:
                py_rel = _ts_to_py_relpath(d.relpath)
                lines.append(f"  ✗ {d.relpath} → missing module {py_rel}")
                continue
            if d.missing_ts_exports:
                names = ", ".join(e.name for e in d.missing_ts_exports)
                lines.append(f"  ✗ {d.relpath}: missing {names}")
            for ts_e, py_kind in d.kind_mismatches:
                lines.append(
                    f"  ✗ {d.relpath}: {ts_e.name} kind mismatch "
                    f"(ts={ts_e.kind}, py={py_kind})"
                )
        lines.append("")
    return "\n".join(lines)


def _format_json(
    ts_files: dict[str, TsFile],
    diffs: list[SurfaceDiff],
    *,
    upstream_root: Path,
    target_root: Path,
) -> str:
    payload = {
        "upstream": str(upstream_root),
        "target": str(target_root),
        "in_sync": not diffs,
        "totals": {
            "ts_files": len(ts_files),
            "ts_exports": sum(len(f.exports) for f in ts_files.values()),
            "files_out_of_parity": len(diffs),
        },
        "out_of_parity": [
            {
                "relpath": d.relpath,
                "missing_module": d.missing_module,
                "missing_exports": [e.name for e in d.missing_ts_exports],
                "kind_mismatches": [
                    {"name": e.name, "ts_kind": e.kind, "py_kind": py_kind}
                    for e, py_kind in d.kind_mismatches
                ],
            }
            for d in diffs
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--upstream",
        type=Path,
        default=Path.home() / "deepseek-harness" / "packages",
        help="Upstream packages root (default: ~/deepseek-harness/packages)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("lca/packages"),
        help="Local mirror root (default: lca/packages)",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit JSON for CI consumption",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Suppress per-file diff listing (useful for CI logs)",
    )
    args = parser.parse_args()

    ts_files, diffs = compare(args.upstream, args.target)
    if args.json_output:
        print(
            _format_json(
                ts_files,
                diffs,
                upstream_root=args.upstream,
                target_root=args.target,
            )
        )
    else:
        out = _format_text(
            ts_files,
            diffs,
            upstream_root=args.upstream,
            target_root=args.target,
        )
        if args.summary_only and diffs:
            head = out.split("\n", 8)[:6]
            print("\n".join(head))
            print(f"... ({len(diffs)} files out of parity; rerun without --summary-only for details)")
        else:
            print(out)
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
