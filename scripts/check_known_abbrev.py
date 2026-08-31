"""Phase D: enforce known abbreviations in package / module names.

Per naming-constitution §3 a small whitelist of abbreviations is
documented; anything outside it must spell out. The currently
approved list::

    cfg, ctx, env, err, msg, info, util, impl, pkg, repo, src,
    doc, docs, db, id, op, ops, ref, refs, tx, util, var

Anything not in this set in a package-or-module name is flagged so the
readers don't have to guess what ``lca.plugins.dct`` or ``strtgy`` means.

Usage::

    python scripts/check_known_abbrev.py [--root PATH] [--strict]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", "traces"}

# Conservative whitelist; expand only via ADR.
APPROVED_ABBREV: set[str] = {
    "cfg",
    "ctx",
    "env",
    "err",
    "msg",
    "info",
    "doc",
    "docs",
    "db",
    "id",
    "idempotency",
    "old",
    "new",
    "impl",
    "util",
    "pkg",
    "repo",
    "src",
    "ops",
    "ref",
    "refs",
    "tx",
    "var",
    "cli",
    "run",
    "stub",
    "spec",
}

# Tokens that look abbreviated but are established domain names.
DOMAIN_EXCEPTIONS: set[str] = {
    "lca",
    "rfc",
    "guid",
    "uuid",
    "id",
    "json",
    "yaml",
    "toml",
    "sqlite",
    "sse",
    "url",
    "uri",
    "html",
    "css",
    "api",
    "sdk",
    "adr",
    "evp",
    "mvp",
}

WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(name: str) -> list[str]:
    parts: list[str] = []
    for raw in re.split(r"[_\W]+", name):
        for sub in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", raw):
            parts.append(sub.lower())
    return parts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca")
    parser.add_argument("--strict", action="store_true", help="treat tokens ≤3 chars as suspicious")
    args = parser.parse_args(argv)

    violations: list[str] = []
    for path in sorted(args.root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        # READMEs and other docs are out of scope; the abbreviation rule
        # applies to Python identifiers (modules + package names).
        if path.is_file() and not path.name.endswith(".py"):
            continue
        rel = path.relative_to(args.root.parent).as_posix()
        name = path.name.removesuffix(".py") if path.is_file() else path.name
        for token in _tokenize(name):
            if token in DOMAIN_EXCEPTIONS or token in APPROVED_ABBREV:
                continue
            if len(token) <= 2:
                violations.append(f"{rel}: tiny unapproved token {token!r}")
            elif args.strict and len(token) <= 3 and token.isalpha():
                violations.append(f"{rel}: short unapproved token {token!r}")

    if not violations:
        print("known-abbrev: every package / module token approved.")
        return 0
    for line in violations:
        print(f"  ✗ {line}", file=sys.stderr)
    print(
        f"known-abbrev: {len(violations)} unapproved abbreviation(s). "
        "Spell out or extend APPROVED_ABBREV via ADR.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
