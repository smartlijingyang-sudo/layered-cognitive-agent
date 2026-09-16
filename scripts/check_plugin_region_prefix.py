"""ADR-0231 D3: enforce ``@plugin(provides=...)`` prefix == ``lca/nodes/<region>/``.

Walks ``lca/nodes/**/*.py`` and parses each ``@plugin(...)`` decorator's
``provides=(...)`` argument. For every provide string of the form ``<prefix>::<id>``,
``<prefix>`` must:

  1. Contain no ``:`` (i.e. ``phase:think::`` / ``region:intervene::`` is rejected).
  2. Equal the file's first directory component under ``lca/nodes/`` — i.e. the
     file ``lca/nodes/think/route/shortcut.py`` must provide ``think::think.shortcut``,
     not ``concept::think.shortcut``.

Failure emits one ``Issue`` per mismatch with file/line and a remediation hint.

Usage:
  python scripts/check_plugin_region_prefix.py [--root PATH] [--json]
  python scripts/check_plugin_region_prefix.py --help
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
NODES_DIR = ROOT / "lca" / "nodes"


@dataclass(frozen=True)
class Issue:
    file: str
    line: int
    plugin_id: str | None
    provides: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def ok(self) -> bool:
        return not self.issues


# --------------------------------------------------------------------------- #
# AST helpers                                                                 #
# --------------------------------------------------------------------------- #


def _resolve_provides_from_call(call_node: ast.Call) -> list[str] | None:
    """Return the literal string list passed as ``provides=...``, or None."""
    for kw in call_node.keywords:
        if kw.arg != "provides":
            continue
        value = kw.value
        if isinstance(value, ast.Tuple):
            out: list[str] = []
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.append(elt.value)
            return out
        if isinstance(value, ast.List):
            return [
                elt.value
                for elt in value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    return None


def _resolve_id_from_call(call_node: ast.Call) -> str | None:
    for kw in call_node.keywords:
        if kw.arg != "id":
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def parse_plugin_decorator(text: str) -> list[dict]:
    """Parse ``@plugin(...)`` decorators from ``text``.

    Returns a list of dicts each with ``provides`` (list[str]) and ``id``
    (str | None) keys. Non-plugin decorators are ignored. The plugin
    decorator may sit on a class (legacy) or a setup function (ADR-0218
    §3.3 — current LCA convention for node plugins); both are picked up.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    decls: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if not isinstance(target, ast.Name):
                continue
            if target.id != "plugin":
                continue
            if not isinstance(dec, ast.Call):
                continue
            provides = _resolve_provides_from_call(dec)
            if provides is None:
                continue
            plugin_id = _resolve_id_from_call(dec)
            owner_name = getattr(node, "name", None)
            decls.append(
                {
                    "provides": provides,
                    "id": plugin_id,
                    "lineno": dec.lineno,
                    "owner": owner_name,
                }
            )
    return decls


# --------------------------------------------------------------------------- #
# Region extraction                                                           #
# --------------------------------------------------------------------------- #


def physical_region_for(rel_path: str | Path) -> str | None:
    """Return the first directory component under ``lca/nodes/``, or None.

    ``lca/nodes/think/route/shortcut.py`` → ``"think"``.
    ``lca/nodes/act/validate/validate.py`` → ``"act"``.
    Anything outside ``lca/nodes/`` → None.
    """
    p = Path(rel_path)
    parts = p.parts
    # Find the "lca/nodes/<region>/..." segment.
    for i, part in enumerate(parts):
        if part == "lca" and i + 2 < len(parts) and parts[i + 1] == "nodes":
            return parts[i + 2]
    return None


def extract_provides_prefixes(provides: list[str]) -> list[str]:
    """Return the prefix (text before ``::``) of each provide string."""
    prefixes: list[str] = []
    for p in provides:
        if "::" in p:
            prefixes.append(p.split("::", 1)[0])
        else:
            # No separator at all — treat the whole string as a malformed prefix.
            prefixes.append(p)
    return prefixes


# --------------------------------------------------------------------------- #
# Per-file validation                                                         #
# --------------------------------------------------------------------------- #


def validate_file(path: Path) -> list[Issue]:
    """Return a list of :class:`Issue` for one plugin file. Empty = OK.

    The path is interpreted relative to ``NODES_DIR``; a file outside
    ``lca/nodes/`` returns an empty list (not this script's jurisdiction).
    """
    rel = path.relative_to(ROOT) if path.is_absolute() and path.is_relative_to(ROOT) else path
    physical = physical_region_for(rel)
    if physical is None:
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    decls = parse_plugin_decorator(text)
    issues: list[Issue] = []
    for decl in decls:
        for provides in decl["provides"]:
            prefixes = extract_provides_prefixes([provides])
            prefix = prefixes[0]
            # Rule 1: no colon-prefixed region (e.g. phase:think, region:intervene).
            if ":" in prefix:
                issues.append(
                    Issue(
                        file=str(rel),
                        line=decl["lineno"],
                        plugin_id=decl["id"],
                        provides=provides,
                        message=(
                            f"region prefix {prefix!r} contains ':' (ADR-0231 D5); "
                            f"expected bare {physical!r} matching physical directory"
                        ),
                    )
                )
                continue
            # Rule 2: prefix must equal the file's physical region directory.
            if prefix != physical:
                issues.append(
                    Issue(
                        file=str(rel),
                        line=decl["lineno"],
                        plugin_id=decl["id"],
                        provides=provides,
                        message=(
                            f"provides prefix {prefix!r} != physical directory "
                            f"{physical!r} (ADR-0231 D3); "
                            f"rewrite as {physical!r}::{provides.split('::', 1)[-1]!r}"
                        ),
                    )
                )
    return issues


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _iter_plugin_files(nodes_dir: Path) -> list[Path]:
    if not nodes_dir.is_dir():
        return []
    out: list[Path] = []
    for p in nodes_dir.rglob("*.py"):
        if p.name == "__init__.py" or "__pycache__" in p.parts:
            continue
        out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(NODES_DIR),
        help="Path to lca/nodes/ (default: %(default)s)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args(argv)

    nodes_dir = Path(args.root).resolve()
    report = Report()
    for path in sorted(_iter_plugin_files(nodes_dir)):
        report.files_scanned += 1
        report.issues.extend(validate_file(path))

    if args.json:
        json.dump(
            {
                "files_scanned": report.files_scanned,
                "issue_count": len(report.issues),
                "issues": [i.to_dict() for i in report.issues],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        if report.ok:
            print(f"OK: scanned {report.files_scanned} plugin files; no region-prefix drift")
        else:
            print(f"FAIL: {len(report.issues)} region-prefix drift(s) in {report.files_scanned} files")
            for issue in report.issues:
                print(
                    f"  {issue.file}:{issue.line} plugin={issue.plugin_id!r} "
                    f"provides={issue.provides!r}"
                )
                print(f"    → {issue.message}")
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
