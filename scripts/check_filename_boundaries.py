"""Enforce filename blacklist/whitelist + legacy_blacklist.

Usage:
    uv run python scripts/check_filename_boundaries.py
    uv run python scripts/check_filename_boundaries.py --strict  # legacy also becomes error
    uv run python scripts/check_filename_boundaries.py --report-only  # just count

Exit codes:
- 0: all clean (or only legacy warnings)
- 1: new violations found, or --strict + legacy violations
- 2: configuration error
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / "pyproject.toml"
LEGACY = ROOT / "legacy_blacklist.txt"

EXCLUDE_DIRS = {"lobehub-ui", "vendor", "node_modules", ".git", "__pycache__", "build", "dist", ".venv"}


@dataclass
class Issue:
    path: str
    kind: str  # "new_violation" | "legacy_warning"
    message: str

    def render(self) -> str:
        prefix = "ERROR" if self.kind == "new_violation" else "WARN "
        return f"{prefix}: {self.path}: {self.message}"


def load_legacy_blacklist() -> set[str]:
    if not LEGACY.exists():
        return set()
    paths: set[str] = set()
    for line in LEGACY.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("#"):
            paths.add(line)
    return paths


def load_package_overrides() -> dict[str, dict[str, list[str]]]:
    """Load filename_whitelist / filename_blacklist_extra per package from pyproject."""
    if not PYPROJECT.exists():
        return {}
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("lca", {}).get("package_contracts", {})
    out: dict[str, dict[str, list[str]]] = {}
    for pkg, cfg in contracts.items():
        wl = cfg.get("filename_whitelist", [])
        bl_extra = cfg.get("filename_blacklist_extra", [])
        if wl or bl_extra:
            out[pkg] = {"whitelist": wl, "blacklist_extra": bl_extra}
    return out


def package_for_path(rel_path: str) -> str | None:
    """Convert a relative path to its dotted package name, if it falls under lca/ or gateway/."""
    parts = rel_path.split("/")
    if not parts:
        return None
    if parts[0] not in ("lca", "gateway"):
        return None
    if len(parts) < 2:
        return parts[0]
    # lca/agent/foo.py -> lca.agent
    # lca/agent/sub/foo.py -> lca.agent.sub (if sub is a package)
    pkg = ".".join(parts[:-1])
    # Only treat as package if it has __init__.py
    pkg_path = ROOT / "/".join(parts[:-1])
    if (pkg_path / "__init__.py").exists():
        return pkg
    # Try shorter
    if len(parts) >= 3:
        short_pkg = ".".join(parts[:2])
        if (ROOT / "/".join(parts[:2]) / "__init__.py").exists():
            return short_pkg
    return ".".join(parts[:2])  # best guess


def all_python_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        files.append(path)
    return files


def check_file(rel_path: str, pkg_overrides: dict[str, dict[str, list[str]]]) -> Issue | None:
    # Whitelist check first
    pkg = package_for_path(rel_path)
    if pkg and pkg in pkg_overrides:
        wl = pkg_overrides[pkg].get("whitelist", [])
        if any(__import__("fnmatch").fnmatch(rel_path, w) for w in wl):
            return None
    # Default whitelist
    from _filename_rules import is_blacklisted, is_whitelisted
    if is_whitelisted(rel_path):
        return None
    # Per-package blacklist extra
    extra_bl: list[str] = []
    if pkg and pkg in pkg_overrides:
        extra_bl = pkg_overrides[pkg].get("blacklist_extra", [])
    if is_blacklisted(rel_path, extra_blacklist=extra_bl):
        from _filename_rules import DEFAULT_BLACKLIST
        patterns = DEFAULT_BLACKLIST + extra_bl
        from fnmatch import fnmatch
        matched = [p for p in patterns if fnmatch(rel_path, p)]
        pat_str = ", ".join(matched) if matched else "blacklist"
        return Issue(rel_path, "new_violation", f"filename matches blacklist ({pat_str}); rename or add to legacy_blacklist.txt")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="treat legacy as error")
    parser.add_argument("--report-only", action="store_true", help="just report counts")
    args = parser.parse_args()

    legacy = load_legacy_blacklist()
    pkg_overrides = load_package_overrides()

    files = all_python_files()
    print(f"Scanning {len(files)} Python files...")

    new_violations: list[Issue] = []
    legacy_warnings: list[Issue] = []

    for path in files:
        rel = str(path.relative_to(ROOT))
        issue = check_file(rel, pkg_overrides)
        if issue is None:
            continue
        if rel in legacy:
            legacy_warnings.append(Issue(rel, "legacy_warning", "filename matches blacklist (in legacy_blacklist.txt)"))
        else:
            new_violations.append(issue)

    print(f"new violations: {len(new_violations)}")
    print(f"legacy warnings: {len(legacy_warnings)}")
    print(f"package overrides: {len(pkg_overrides)}")

    if args.report_only:
        return 0

    for issue in new_violations:
        print(issue.render())
    for issue in legacy_warnings:
        print(issue.render())

    if new_violations:
        return 1
    if args.strict and legacy_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
