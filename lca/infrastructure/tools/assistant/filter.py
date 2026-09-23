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

# ADR-0248 平台系统工具：gated 模式下声带与员工电脑沙箱核心工具，不受 assistant
# tools.yaml/grants.yaml 策略过滤（否则「模型看得到但 body 未注册或被策略误杀」）。
_VOCAL_SYSTEM_TOOLS: frozenset[str] = frozenset(
    {
        "send_message",
        "box_read_file",
        "box_write_file",
        "box_list_files",
        "box_run_command",
        "request_box_help",
    }
)


_ToolSet: TypeAlias = tuple[Tool, ...]


def _tool_matching_names(tool: Tool) -> frozenset[str]:
    """Extract all valid matching identifier keys for a tool."""
    name = tool.name
    keys: set[str] = {name}
    if name.startswith("local_"):
        keys.add(name[6:])
    elif name.startswith("mcp__"):
        parts = name.split("__", 2)
        keys.add("mcp")
        if len(parts) > 1 and parts[1]:
            keys.add(parts[1])
        if len(parts) > 2 and parts[2]:
            keys.add(parts[2])
    return frozenset(keys)


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
        keys = _tool_matching_names(tool)
        if bool(keys & deny):
            continue
        required_grant = _required_grant(tool)
        if required_grant:
            if required_grant in grants:
                kept.append(tool)
            continue
        if not allow or bool(keys & allow):
            kept.append(tool)
        elif bool(keys & _VOCAL_SYSTEM_TOOLS):
            # 声带系统工具始终保留（gated 唯一发声通道，见模块 docstring）。
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
