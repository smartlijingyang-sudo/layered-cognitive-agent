"""Generate [tool.lca.package_contracts.*] sections for pyproject.toml
from existing README.md files.

Usage:
    uv run python scripts/scaffold_pyproject_contracts.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / "pyproject.toml"

EXCLUDE_DIRS = {"lobehub-ui", "vendor", "node_modules", ".git", "__pycache__", "build", "dist"}


def discover_packages() -> list[str]:
    """Find all LCA packages that have README.md."""
    pkgs = []
    for top in ("lca", "gateway"):
        top_dir = ROOT / top
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


def parse_readme_sections(readme_path: Path) -> dict[str, str]:
    """Parse 9 sections from a README.md."""
    text = readme_path.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    for match in re.finditer(
        r"^## (\d+)\. (.+?)\n(.*?)(?=\n## |\Z)", text, re.MULTILINE | re.DOTALL
    ):
        _num, title, body = match.groups()
        sections[title.strip()] = body.strip()
    return sections


def parse_dependencies(dep_string: str) -> list[str]:
    """Parse a comma-separated dependency string into a list."""
    if not dep_string or dep_string == "（与 pyproject.allowed_dependencies 镜像）":
        return []
    return [d.strip() for d in dep_string.split(",") if d.strip()]


def generate_section(package: str, readme_path: Path) -> str:
    """Generate a [tool.lca.package_contracts.\"<pkg>\"] section."""
    sections = parse_readme_sections(readme_path)
    responsibility = sections.get("职责", "").replace("\n", " ").strip()
    not_resp = sections.get("不负责", "").replace("\n", " ").strip()
    allowed = parse_dependencies(sections.get("允许依赖", ""))
    forbidden = parse_dependencies(sections.get("禁止依赖", ""))
    side_effects = parse_dependencies(sections.get("副作用", ""))
    public_api = parse_dependencies(sections.get("公共入口", ""))

    def toml_list(items: list[str]) -> str:
        if not items:
            return "[]"
        inner = ",\n    ".join(f'"{x}"' for x in items)
        return f"[\n    {inner},\n]"

    return f'''[tool.lca.package_contracts."{package}"]
responsibility = "{toml_escape(responsibility)}"
not_responsible_for = "{toml_escape(not_resp)}"
allowed_dependencies = {toml_list(allowed)}
forbidden_dependencies = {toml_list(forbidden)}
side_effects = {toml_list(side_effects)}
public_api = {toml_list(public_api)}
schema_version = "1.0.0"
'''


def toml_escape(s: str) -> str:
    """Escape a string for TOML."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    packages = discover_packages()
    print(f"discovered {len(packages)} packages")

    # Read existing pyproject.toml
    existing = PYPROJECT.read_text(encoding="utf-8")

    # Remove old [tool.lca.package_contracts.*] sections (any depth)
    # Find the position of the FIRST section and cut everything from there to end
    match = re.search(r"^\[tool\.lca\.package_contracts", existing, re.MULTILINE)
    if match:
        new_content = existing[: match.start()].rstrip() + "\n\n"
    else:
        new_content = existing.rstrip() + "\n\n"

    # Generate new section
    new_section = "[tool.lca.package_contracts]\n\n"
    for pkg in packages:
        readme = ROOT / pkg.replace(".", "/") / "README.md"
        if readme.exists():
            new_section += generate_section(pkg, readme) + "\n"

    output = new_content + new_section

    if args.dry_run:
        print(output[:2000])
        return 0

    PYPROJECT.write_text(output, encoding="utf-8")
    print(f"wrote {len(packages)} sections to pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
