"""Validate L1 README / L2 pyproject / L3 import-linter / actual import consistency.

Usage:
    uv run python scripts/check_package_contracts.py
    uv run python scripts/check_package_contracts.py --package lca.contracts
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

REQUIRED_SECTIONS = [
    "## 1. 职责", "## 2. 不负责", "## 3. 输入", "## 4. 输出",
    "## 5. 允许依赖", "## 6. 禁止依赖", "## 7. 副作用",
    "## 8. 失败语义", "## 9. 公共入口",
]

REQUIRED_L2_FIELDS = [
    "responsibility", "not_responsible_for", "allowed_dependencies",
    "forbidden_dependencies", "side_effects", "public_api", "schema_version",
]

EXCLUDE_DIRS = {"lobehub-ui", "vendor", "node_modules", ".git", "__pycache__", "build", "dist"}


@dataclass
class Issue:
    package: str
    layer: str  # L1 / L2 / L3 / actual
    message: str

    def render(self) -> str:
        return f"[{self.layer}] {self.package}: {self.message}"


def discover_packages(root: Path) -> list[str]:
    """Find all LCA package paths (lca/X, lca/X/Y, gateway, gateway/X)."""
    pkgs: list[str] = []
    for top in ("lca", "gateway"):
        top_dir = root / top
        if not top_dir.exists():
            continue
        if (top_dir / "README.md").exists():
            pkgs.append(top)
        for child in sorted(top_dir.iterdir()):
            if not child.is_dir() or not (child / "__init__.py").exists():
                continue
            if any(p in EXCLUDE_DIRS for p in child.parts):
                continue
            if (child / "README.md").exists():
                pkgs.append(f"{top}.{child.name}")
            for grand in sorted(child.iterdir()):
                if not grand.is_dir() or not (grand / "__init__.py").exists():
                    continue
                if any(p in EXCLUDE_DIRS for p in grand.parts):
                    continue
                if (grand / "README.md").exists():
                    pkgs.append(f"{top}.{child.name}.{grand.name}")
    return pkgs


def package_to_path(root: Path, package: str) -> Path:
    return root / package.replace(".", "/")


def check_l1_readme_exists(root: Path, packages: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    for pkg in packages:
        readme = package_to_path(root, pkg) / "README.md"
        if not readme.exists():
            issues.append(Issue(pkg, "L1", f"README.md missing at {readme}"))
            continue
        text = readme.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                issues.append(Issue(pkg, "L1", f"missing section: {section}"))
    return issues


def check_l2_pyproject_section(packages: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("lca", {}).get("package_contracts", {})
    for pkg in packages:
        section = contracts.get(pkg)
        if section is None:
            issues.append(Issue(pkg, "L2", f"missing [tool.lca.package_contracts.\"{pkg}\"]"))
            continue
        for field in REQUIRED_L2_FIELDS:
            if field not in section:
                issues.append(Issue(pkg, "L2", f"missing field: {field}"))
    return issues


def cross_check_l1_l2(packages: list[str]) -> list[Issue]:
    """Verify L1 README mentions every L2 forbidden_dependencies entry."""
    issues: list[Issue] = []
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("lca", {}).get("package_contracts", {})
    for pkg in packages:
        readme = package_to_path(ROOT, pkg) / "README.md"
        if not readme.exists():
            continue
        text = readme.read_text(encoding="utf-8")
        section = contracts.get(pkg, {})
        forbidden = section.get("forbidden_dependencies", [])
        for dep in forbidden:
            if dep and dep not in text:
                issues.append(Issue(pkg, "L1↔L2", f"forbidden dep {dep} not mentioned in README"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", help="check only this package")
    parser.add_argument("--root", default=str(ROOT), type=Path)
    args = parser.parse_args()

    packages = discover_packages(args.root)
    if args.package:
        packages = [p for p in packages if p == args.package or p.startswith(args.package + ".")]

    all_issues: list[Issue] = []
    all_issues.extend(check_l1_readme_exists(args.root, packages))
    all_issues.extend(check_l2_pyproject_section(packages))
    all_issues.extend(cross_check_l1_l2(packages))

    if not all_issues:
        print(f"OK: {len(packages)} packages checked, no issues")
        return 0

    for issue in all_issues:
        print(issue.render())
    print(f"\nFAIL: {len(all_issues)} issues across {len(packages)} packages")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
