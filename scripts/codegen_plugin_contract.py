#!/usr/bin/env python
"""ADR-0110 PR-C codemod: convert ``logic_address=LogicAddress(...)`` to
``contract=PluginContract(...)``.

This is the **preview** script for PR-C (the 194-file rollout per ADR-0110
§六). It targets the highly-uniform ``control_contributions/`` and similar
canonical plugin files where all 6 LogicAddress dimensions are present in
the same column-aligned shape. For each input file:

  1. Replace ``logic_address=LogicAddress(\n        functional_group=...,\n        control_slot=...,\n        scope=...,\n        authority=...,\n        evidence=...,\n        revision=...,\n    ),`` with ``contract=PluginContract(\n        identity=PluginIdentity(version=...),\n        architecture=ArchitectureContract(group=..., control_slots=(...,)),\n        lifecycle=LifecycleContract(allowed_scopes=(...,)),\n        authority=AuthorityContract(grants=...),\n        observability=EvidenceContract(descriptors=...),\n    ),``
  2. Update imports: drop ``LogicAddress``, add ``PluginContract`` sections.

Files that don't match the expected column-aligned shape are **left alone**
and reported — the broader 194-file codemod PR needs a richer transformer;
this script is the safe subset for trial.

Usage:
    uv run python scripts/codegen_plugin_contract.py [--dry-run] <file.py> [<file.py> ...]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence

# Match the column-aligned full-blocks pattern seen in the canonical plugin files.
# Capture: fg_value, slot_value, scope_value, authority_value, evidence_value, revision_value.
# Note: ``authority`` / ``evidence`` are tuples containing commas (``("a", "b")``),
# so the inner capture must allow ``,`` but NOT ``\n`` — capture to end-of-line.
# Match the column-aligned full-blocks pattern, supporting multi-line tuples
# for ``evidence=`` and ``authority=`` (some plugin files have parenthesised
# continuation like:
#     evidence=(
#         "name.checked",
#         "name-2.checked",
#     ),
# ).
#
# Strategy: capture each kwarg value to the closing "," / ")" at the same
# indent column. Multi-line values use a greedy match into subsequent
# parenthesised body lines.
_BLOCK_RE = re.compile(
    r"^(?P<indent>[ \t]*)logic_address=LogicAddress\("
    r"\n[ \t]+functional_group=(?P<fg>[^,\n]+),"
    r"\n[ \t]+control_slot=(?P<slot>[^,\n]+),"
    r"\n[ \t]+scope=(?P<scope>[^,\n]+),"
    r"\n[ \t]+authority=(?P<authority>"
    r"(?:\([^)]*\)|[^\n]+)"  # either single-line tuple or scalar
    r"),"
    r"\n[ \t]+evidence=(?P<evidence>"
    r"(?:\((?:[^()]|\([^()]*\))*\)|[^\n]+)"  # nested or single-line tuple, or scalar
    r"),"
    r"\n[ \t]+revision=(?P<revision>[^\n]+),"
    r"\n[ \t]*\),",
    re.MULTILINE | re.VERBOSE,
)

_PLUGIN_CONTRACT_IMPORT = (
    "from lca.contracts.harness.composition.plugin_contract import (\n"
    "    ArchitectureContract,\n"
    "    AuthorityContract,\n"
    "    EvidenceContract,\n"
    "    LifecycleContract,\n"
    "    PluginContract,\n"
    "    PluginIdentity,\n"
    ")\n"
)


def _to_plugin_contract_block(match: re.Match[str]) -> str:
    fg = match.group("fg").strip()
    slot = match.group("slot").strip()
    scope = match.group("scope").strip()
    authority = match.group("authority").strip()
    evidence = match.group("evidence").strip()
    revision = match.group("revision").strip()

    indent = match.group("indent") or ""
    return (
        f"{indent}contract=PluginContract(\n"
        f"{indent}    identity=PluginIdentity(version={revision}),\n"
        f"{indent}    architecture=ArchitectureContract(group={fg}, control_slots=({slot},)),\n"
        f"{indent}    lifecycle=LifecycleContract(allowed_scopes=({scope},)),\n"
        f"{indent}    authority=AuthorityContract(grants={authority}),\n"
        f"{indent}    observability=EvidenceContract(descriptors={evidence}),\n"
        f"{indent}),"
    )


def _swap_imports(text: str) -> str:
    """Drop the LogicAddress import; add the PluginContract import block."""
    text = re.sub(
        r"^from lca\.contracts\.protocols\.composition\.logic_address import LogicAddress\n",
        "",
        text,
        flags=re.MULTILINE,
    )

    if "PluginContract" not in text:
        return text
    if re.search(
        r"^from lca\.contracts\.harness\.composition\.plugin_contract import", text, re.MULTILINE
    ):
        return text

    insert_after = re.search(r"^(from lca\.contracts\.[^\n]+)\n", text, re.MULTILINE)
    if insert_after:
        idx = insert_after.end()
        return text[:idx] + "\n" + _PLUGIN_CONTRACT_IMPORT + text[idx:]
    fut = re.search(r"^from __future__ import annotations\n", text, re.MULTILINE)
    if fut:
        return text[: fut.end()] + "\n" + _PLUGIN_CONTRACT_IMPORT + text[fut.end() :]
    return _PLUGIN_CONTRACT_IMPORT + "\n" + text


def codemod_file(path: str, *, dry_run: bool) -> tuple[int, int]:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    new_text = _BLOCK_RE.sub(_to_plugin_contract_block, text)
    n_subs = len(_BLOCK_RE.findall(text))
    new_text = _swap_imports(new_text)

    if new_text != text and not dry_run:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
    return n_subs, 1 if n_subs else 0


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("files", nargs="+", help="Files to codemod")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args(argv[1:])

    for path in args.files:
        n_subs, touched = codemod_file(path, dry_run=args.dry_run)
        action = "would replace" if args.dry_run else "replaced"
        if n_subs == 0:
            print(f"skip {path} (no matching block)")
        elif touched:
            print(f"{action} {n_subs} block(s) in {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
