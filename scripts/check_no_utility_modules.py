"""Phase D: reject generic-named modules outside an explicit whitelist.

Per _filename_rules.DEFAULT_BLACKLIST (``*util*.py``, ``*helper*.py``,
``*manager*.py``, ``*impl*.py``, ``*common*.py``, ``*misc*.py``) plus
naming-constitution §5: every Python module name must be a domain noun,
not a category-of-file placeholder name. ``__init__.py`` is exempted;
opt-in overrides live in
``pyproject.toml [tool.lca.package_contracts.<pkg>].filename_whitelist``.

Usage::

    python scripts/check_no_utility_modules.py [--root PATH]
"""
from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "scripts"))
from _filename_rules import DEFAULT_BLACKLIST, is_whitelisted  # noqa: E402

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


def _package_whitelists(root: Path) -> dict[str, list[str]]:
    config_path = root / "pyproject.toml"
    if not config_path.exists():
        return {}
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    contracts = config.get("tool", {}).get("lca", {}).get("package_contracts", {})
    out: dict[str, list[str]] = {}
    for pkg, body in contracts.items():
        if isinstance(body, dict):
            wl = body.get("filename_whitelist")
            if isinstance(wl, list):
                out[pkg] = list(wl)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca")
    args = parser.parse_args(argv)

    pkg_wl = _package_whitelists(args.root.parent)
    extras: list[str] = []
    for wl in pkg_wl.values():
        extras.extend(wl)

    violations: list[str] = []
    for py in sorted(args.root.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = py.relative_to(args.root.parent).as_posix()
        if is_whitelisted(rel, package_whitelist=extras):
            continue
        for pattern in DEFAULT_BLACKLIST:
            if fnmatch.fnmatch(py.name, pattern):
                violations.append(rel)
                break

    if not violations:
        print("no-utility-modules: every module name is a domain noun.")
        return 0
    for rel in violations:
        print(f"  ✗ {rel}", file=sys.stderr)
    print(
        f"no-utility-modules: {len(violations)} generic-named module(s). "
        "Rename to a domain noun (or register an exempt in pyproject.toml "
        "[tool.lca.package_contracts.<pkg>].filename_whitelist).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
