"""Auto-sync L1 README 段 9 公共入口 with __init__.py __all__.

Phase 1 auto-generated L1 段 9 with the package name as a placeholder.
This script extracts the actual __all__ from each __init__.py and updates
the L1 README 段 9 to list all exported symbols.

Usage:
    uv run python scripts/sync_l1_public_api.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
EXCLUDE_DIRS = {
    "lobehub-ui",
    "vendor",
    "node_modules",
    ".git",
    "__pycache__",
    "build",
    "dist",
    ".venv",
}


def discover_packages_with_readme() -> list[Path]:
    """Find all package directories (have __init__.py + README.md)."""
    out: list[Path] = []
    for top in ("lca", "gateway"):
        top_dir = ROOT / top
        if not top_dir.exists():
            continue
        for path in sorted(top_dir.rglob("__init__.py")):
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            pkg_dir = path.parent
            readme = pkg_dir / "README.md"
            if readme.exists():
                out.append(pkg_dir)
    return out


def extract_all_symbols(init_path: Path) -> list[str]:
    """Extract symbols from __all__ in __init__.py."""
    try:
        text = init_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    match = re.search(r"^__all__\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    body = match.group(1)
    # Strip comments (line-starting #)
    body = re.sub(r"#[^\n]*", "", body)
    symbols: list[str] = []
    for sym in body.split(","):
        sym = sym.strip().strip("'\"")
        if sym and sym != "*":
            symbols.append(sym)
    return symbols


def update_readme_section(readme_path: Path, new_section: str, dry_run: bool) -> bool:
    """Replace the 段 9 公共入口 section. Returns True if changed."""
    try:
        text = readme_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    # Match the 段 9 section (everything from "## 9. 公共入口" until next "## " or end)
    pattern = re.compile(
        r"## 9\.\s*公共入口\s*\n.*?(?=\n## |\Z)",
        re.DOTALL,
    )
    new_text = pattern.sub(new_section.rstrip() + "\n\n", text)
    if new_text == text:
        return False
    if not dry_run:
        readme_path.write_text(new_text, encoding="utf-8")
    return True


def render_section(symbols: list[str]) -> str:
    if not symbols:
        return "## 9. 公共入口\n（无显式 __all__；通过模块导入即可）\n\n"
    # Wrap symbols into a backtick-quoted list
    quoted = ", ".join(f"`{s}`" for s in symbols)
    return f"## 9. 公共入口\n{quoted}\n\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    packages = discover_packages_with_readme()
    print(f"Discovered {len(packages)} packages with README + __init__.py")

    changed = 0
    skipped = 0
    for pkg_dir in packages:
        init = pkg_dir / "__init__.py"
        readme = pkg_dir / "README.md"
        symbols = extract_all_symbols(init)
        new_section = render_section(symbols)
        if update_readme_section(readme, new_section, args.dry_run):
            changed += 1
        else:
            skipped += 1

    print(f"{'Would change' if args.dry_run else 'Changed'}: {changed}")
    print(f"Skipped (already correct): {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
