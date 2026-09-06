#!/usr/bin/env python3
"""Cognitive directory discipline gate (docs/specs/cognitive-directory-discipline.md).

Checks anchor packages for:
- Direct .py count per directory (default ≤5)
- File line count (default ≤300, legacy 400)
- Redundant naming (*_emit outside emit/, etc.)

Usage:
    uv run python scripts/check_cognitive_directory.py
    uv run python scripts/check_cognitive_directory.py --report-only
    uv run python scripts/check_cognitive_directory.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
ANCHORS_FILE = Path(__file__).resolve().parent / "cognitive_directory_anchors.toml"
SKIP_DIRS = frozenset({"__pycache__", ".git", ".venv", "node_modules", "vendor", "lobehub-ui", "traces"})

# Suffix must appear under a path segment matching the key (directory name).
CONTEXT_SUFFIX_RULES: dict[str, re.Pattern[str]] = {
    "_emit": re.compile(r"(^|/)emit(/|$)|(^|/)fact_emit(/|$)"),
    "_append": re.compile(r"(^|/)append(/|$)|(^|/)session/append\.py$"),
    "_commit": re.compile(r"(^|/)commit(/|$)"),
}


@dataclass
class Violation:
    kind: str
    path: str
    message: str

    def render(self) -> str:
        return f"  [{self.kind}] {self.path}: {self.message}"


@dataclass
class Report:
    violations: list[Violation] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)

    def add(self, v: Violation, *, warning: bool = False) -> None:
        (self.warnings if warning else self.violations).append(v)


def _load_config() -> dict:
    if not ANCHORS_FILE.is_file():
        return {"defaults": {}, "anchors": [], "legacy_allow": []}
    with ANCHORS_FILE.open("rb") as f:
        return tomllib.load(f)


def _direct_py_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix == ".py" and p.name not in ("__init__.py", "__main__.py")
    )


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def _is_plugin_py(rel_posix: str) -> bool:
    return rel_posix.endswith("/plugin.py") or rel_posix.endswith("plugin.py")


def _check_directory_size(
    directory: Path,
    *,
    max_direct: int,
    max_warn: int,
    legacy_cap: int | None,
    report: Report,
    rel_base: Path,
) -> None:
    rel_dir = str(directory.relative_to(rel_base))
    py_files = _direct_py_files(directory)
    count = len(py_files)
    cap = legacy_cap if legacy_cap is not None else max_direct
    if count > cap:
        report.add(
            Violation(
                "dir_overflow",
                rel_dir,
                f"{count} direct .py files (cap {cap})",
            )
        )
    elif count > max_warn and legacy_cap is None:
        report.add(
            Violation(
                "dir_warn",
                rel_dir,
                f"{count} direct .py files (warn above {max_direct})",
            ),
            warning=True,
        )


def _check_file_loc(
    path: Path,
    *,
    max_loc: int,
    max_legacy: int,
    plugin_max: int,
    loc_legacy_caps: dict[str, int],
    report: Report,
    rel_base: Path,
    strict_loc: bool,
) -> None:
    rel = str(path.relative_to(rel_base))
    loc = _line_count(path)
    file_cap = loc_legacy_caps.get(rel)
    if file_cap is not None:
        limit = file_cap
    else:
        limit = plugin_max if _is_plugin_py(rel) else max_legacy if strict_loc else max_loc
    target = max_loc if not file_cap else min(max_loc, file_cap)
    if loc <= target:
        return
    if loc <= limit:
        report.add(
            Violation("loc_warn", rel, f"{loc} lines (target ≤{target}, hard cap {limit})"),
            warning=True,
        )
        return
    report.add(Violation("loc_overflow", rel, f"{loc} lines (cap {limit})"))


def _check_redundant_naming(path: Path, rel_base: Path, report: Report) -> None:
    rel = str(path.relative_to(rel_base))
    if path.name == "__init__.py":
        return
    stem = path.stem
    parent_parts = path.relative_to(rel_base).parts[:-1]
    for part in parent_parts:
        if stem.startswith(f"{part}_") and len(stem) > len(part) + 1:
            report.add(
                Violation(
                    "redundant_prefix",
                    rel,
                    f"filename repeats parent directory '{part}'",
                ),
                warning=True,
            )
            break
    for suffix, pattern in CONTEXT_SUFFIX_RULES.items():
        if stem.endswith(suffix) or suffix.strip("_") in stem.split("_"):
            if suffix == "_append" and path.name == "append.py":
                continue
            if not pattern.search(rel):
                report.add(
                    Violation(
                        "context_suffix",
                        rel,
                        f"'{suffix}' suffix outside semantic directory (see cognitive-directory-discipline §4.2)",
                    ),
                    warning=True,
                )


def _walk_tree(root: Path, rel_base: Path) -> list[Path]:
    dirs: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if _direct_py_files(path):
            dirs.append(path)
    return dirs


def _legacy_loc_caps(config: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for entry in config.get("legacy_loc_allow", []):
        out[str(entry["path"])] = int(entry["max_loc"])
    return out


def _legacy_caps(config: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for entry in config.get("legacy_allow", []):
        out[str(entry["path"])] = int(entry["max_direct_py"])
    return out


def _strict_directories(config: dict) -> list[Path]:
    """Directories that must comply at merge time (anchor root + strict_children)."""
    dirs: list[Path] = []
    for anchor in config.get("anchors", []):
        anchor_path = ROOT / anchor["path"]
        if anchor_path.is_dir():
            dirs.append(anchor_path)
        for child in anchor.get("strict_children", []):
            child_path = anchor_path / child
            if child_path.is_dir():
                dirs.append(child_path)
    return dirs


def check_anchors(
    config: dict,
    *,
    report_only: bool,
    deep: bool,
) -> Report:
    defaults = config.get("defaults", {})
    max_direct = int(defaults.get("max_direct_py", 5))
    max_warn = int(defaults.get("max_direct_py_warn", 6))
    max_loc = int(defaults.get("max_file_loc", 300))
    max_legacy = int(defaults.get("max_file_loc_legacy", 400))
    plugin_max = int(defaults.get("plugin_py_max_loc", 500))
    legacy_caps = _legacy_caps(config)
    loc_legacy_caps = _legacy_loc_caps(config)
    report = Report()

    if deep:
        scan_roots = [ROOT / a["path"] for a in config.get("anchors", []) if (ROOT / a["path"]).is_dir()]
        directories: list[Path] = []
        for root in scan_roots:
            directories.extend(_walk_tree(root, ROOT))
    else:
        directories = _strict_directories(config)

    for directory in directories:
        rel_dir = str(directory.relative_to(ROOT))
        legacy_cap = legacy_caps.get(rel_dir)
        _check_directory_size(
            directory,
            max_direct=max_direct,
            max_warn=max_warn,
            legacy_cap=legacy_cap,
            report=report,
            rel_base=ROOT,
        )
        for py_file in _direct_py_files(directory) + (
            [directory / "__init__.py"] if (directory / "__init__.py").is_file() else []
        ):
            if py_file.name == "__init__.py" and _line_count(py_file) < 80:
                continue
            strict_loc = not deep and not report_only
            _check_file_loc(
                py_file,
                max_loc=max_loc,
                max_legacy=max_legacy,
                plugin_max=plugin_max,
                loc_legacy_caps=loc_legacy_caps,
                report=report,
                rel_base=ROOT,
                strict_loc=strict_loc,
            )
            if not deep:
                _check_redundant_naming(py_file, ROOT, report)

    return report


def scan_full_inventory(config: dict) -> Report:
    """Report-only scan of lca/ for directory overflows (no loc strict)."""
    defaults = config.get("defaults", {})
    max_direct = int(defaults.get("max_direct_py", 5))
    legacy_caps = _legacy_caps(config)
    report = Report()
    lca = ROOT / "lca"
    if not lca.is_dir():
        return report
    for directory in _walk_tree(lca, ROOT):
        rel_dir = str(directory.relative_to(ROOT))
        legacy_cap = legacy_caps.get(rel_dir)
        cap = legacy_cap if legacy_cap is not None else max_direct
        count = len(_direct_py_files(directory))
        if count > cap:
            kind = "legacy_overflow" if legacy_cap else "inventory_overflow"
            report.add(
                Violation(kind, rel_dir, f"{count} direct .py (cap {cap})"),
                warning=bool(legacy_cap),
            )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="inventory only, no fail on anchors")
    parser.add_argument("--deep", action="store_true", help="recursive scan under anchors (report inventory)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    config = _load_config()
    anchor_report = check_anchors(config, report_only=args.report_only, deep=args.deep)

    if args.report_only:
        inventory = scan_full_inventory(config)
        anchor_report.warnings.extend(inventory.warnings)
        anchor_report.violations.extend(inventory.violations)

    if args.json:
        payload = {
            "violations": [asdict(v) for v in anchor_report.violations],
            "warnings": [asdict(v) for v in anchor_report.warnings],
        }
        print(json.dumps(payload, indent=2))
        return 1 if anchor_report.violations else 0

    if anchor_report.violations:
        print("check_cognitive_directory: FAIL", file=sys.stderr)
        for v in anchor_report.violations:
            print(v.render(), file=sys.stderr)
    else:
        print("check_cognitive_directory: OK (anchors)")

    if anchor_report.warnings:
        print(f"check_cognitive_directory: {len(anchor_report.warnings)} warning(s)", file=sys.stderr)
        for v in anchor_report.warnings[:30]:
            print(v.render(), file=sys.stderr)
        if len(anchor_report.warnings) > 30:
            print(f"  ... and {len(anchor_report.warnings) - 30} more", file=sys.stderr)

    return 1 if anchor_report.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
