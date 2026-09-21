"""Assistant Home tool filtering (ADR-0242 D4 / I-B3).

``filter_tools_by_assistant`` is the runtime consumer of a Home's
``tools.yaml`` / ``grants.yaml``: after the generic tool set is materialized
for a run, this pure function narrows it to what the assistant's Home policy
permits.  The decision is data-driven — every assistant difference lives in
its Home, not in plugin code (ADR-0242 D9).

Semantics:

- A tool that declares a ``required_grant`` is kept only when that grant is
  present in ``grants.yaml.grants`` (grant set filters grant-requiring tools).
- A tool without a grant requirement is kept unless denied; a non-empty
  ``tools.yaml.allow`` narrows those tools to the listed names.
- ``tools.yaml.deny`` always wins.
- Fail-closed (C5 衰减): a missing or malformed ``tools.yaml`` denies
  everything; a missing/malformed ``grants.yaml`` denies every tool that
  requires a grant.

The legacy no-``assistant_id`` path never calls this function, so
web-standard behavior is untouched (I-B8).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TypeAlias

import yaml

from lca.contracts.protocols.runtime.infra.infra import Tool

__all__ = ["filter_tools_by_assistant"]

_ToolSet: TypeAlias = tuple[Tool, ...]


def filter_tools_by_assistant(
    tools: Iterable[Tool],
    home_path: str | Path,
) -> _ToolSet:
    """Narrow ``tools`` to the assistant Home's tool policy.

    ``grants.yaml`` is the only source of grant coverage: a tool with a
    ``required_grant`` is kept iff that grant is in the grant set.  Tools
    without a grant requirement are kept by default, unless a non-empty
    ``tools.yaml.allow`` name-allowlist excludes them or ``deny`` lists them.
    """
    home = Path(home_path)
    policy = _load_tools_policy(home)
    if policy is None:
        return ()
    allow, deny = policy
    grants = _load_grants(home)

    kept: list[Tool] = []
    for tool in tools:
        name = tool.name
        base_name = name[6:] if name.startswith("local_") else name
        if name in deny or base_name in deny:
            continue
        if name.startswith("mcp__"):
            parts = name.split("__", 2)
            server_name = parts[1] if len(parts) > 1 else ""
            raw_tool_name = parts[2] if len(parts) > 2 else ""
            if (
                "mcp" in deny
                or (server_name and server_name in deny)
                or (raw_tool_name and raw_tool_name in deny)
            ):
                continue
            if (
                not allow
                or "mcp" in allow
                or name in allow
                or (server_name and server_name in allow)
                or (raw_tool_name and raw_tool_name in allow)
            ):
                kept.append(tool)
            continue
        required_grant = _required_grant(tool)
        if required_grant:
            if required_grant in grants:
                kept.append(tool)
            continue
        if not allow or name in allow or base_name in allow:
            kept.append(tool)
    return tuple(kept)


def _load_tools_policy(home: Path) -> tuple[frozenset[str], frozenset[str]] | None:
    """Read ``tools.yaml`` as ``(allow, deny)``; ``None`` = deny-all.

    ``None`` (missing file / YAML error / wrong shape) is the fail-closed
    signal: the caller returns an empty tool set rather than guessing.
    """
    path = home / "tools.yaml"
    if not path.is_file():
        return None
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    tools = parsed.get("tools")
    if not isinstance(tools, dict):
        return None
    allow = tools.get("allow")
    deny = tools.get("deny")
    if not isinstance(allow, list) or not isinstance(deny, list):
        return None
    return _non_empty_strings(allow), _non_empty_strings(deny)


def _load_grants(home: Path) -> frozenset[str]:
    """Read the ``grants`` list from ``grants.yaml``; failures yield empty.

    Empty is the narrowest grant set: tools that require a grant are denied
    (C5), while grant-agnostic tools remain governed by ``tools.yaml`` alone.
    """
    path = home / "grants.yaml"
    if not path.is_file():
        return frozenset()
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return frozenset()
    if not isinstance(parsed, dict):
        return frozenset()
    grants = parsed.get("grants")
    if not isinstance(grants, list):
        return frozenset()
    return _non_empty_strings(grants)


def _required_grant(tool: Tool) -> str:
    """Return the tool's declared grant requirement, or ``""`` when none.

    The ``Tool`` protocol does not carry a grant field; tools that need one
    declare ``required_grant`` as a class attribute.  Absence means the tool
    is grant-agnostic and is governed by ``tools.yaml`` alone.
    """
    return str(getattr(tool, "required_grant", "") or "").strip()


def _non_empty_strings(items: Iterable[object]) -> frozenset[str]:
    """Normalize policy entries to non-empty strings (non-strings vanish)."""
    return frozenset(str(item).strip() for item in items if isinstance(item, str) and item.strip())
