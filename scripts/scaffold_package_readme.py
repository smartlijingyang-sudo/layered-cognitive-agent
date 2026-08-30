"""Scaffold README.md for LCA packages from 9-field contract metadata.

Usage:
    uv run python scripts/scaffold_package_readme.py <package_path> --meta key=value

Example:
    uv run python scripts/scaffold_package_readme.py lca/contracts \\
        --meta responsibility="数据契约层" \\
        --meta not_responsible_for="实现细节、I/O" \\
        --meta allowed_dependencies="" \\
        --meta forbidden_dependencies="lca.infrastructure,lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins" \\
        --meta side_effects="" \\
        --meta public_api="lca.contracts.models,lca.contracts.protocols"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "docs" / "templates" / "PACKAGE_README.md"


def render_template(package_name: str, owner: str, meta: dict[str, str]) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template.replace("{{package_name}}", package_name)
    rendered = rendered.replace("{{owner}}", owner)
    for key, value in meta.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_path", help="e.g. lca/contracts")
    parser.add_argument(
        "--meta",
        action="append",
        default=[],
        help="key=value (repeatable)",
    )
    parser.add_argument("--owner", default="@lca-maintainers")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    meta: dict[str, str] = {}
    for kv in args.meta:
        if "=" not in kv:
            print(f"bad --meta: {kv}", file=sys.stderr)
            return 2
        k, v = kv.split("=", 1)
        meta[k] = v

    package_name = args.package_path.rstrip("/").replace("/", ".")
    rendered = render_template(package_name, args.owner, meta)
    target = Path(args.package_path) / "README.md"

    if args.dry_run:
        print(f"would write {target} ({len(rendered)} chars)")
        return 0

    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
