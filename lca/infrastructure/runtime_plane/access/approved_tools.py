"""Per-run approved-tool context for the authorization gate.

工具权限审批通过后，carrier 把被批准的工具名记在
``RunSession.approved_tool_names``（跨请求持久）。resume 任务启动时把这份
集合注入当前 context，``act.authorize`` 读取它放行同一 run 内已批准工具的
再次调用，避免 full-restart resume 的「审批→重调→再审批」循环。

ContextVar 只随 resume 任务生命周期存活，天然按 run/task 隔离。
"""

from __future__ import annotations

import contextvars

_approved_tools_var: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "lca_approved_tool_names",
    default=frozenset(),
)


def canonical_tool_name(name: str) -> str:
    """归一化工具名为规范形（camelCase，LobeHub wire 约定），幂等。

    ``execute_code`` → ``executeCode``；``executeCode`` 保持原样。LLM 视提示
    上下文随机发射 snake_case 或 camelCase，审批记录与放行检查都用规范形，
    避免「批准了 execute_code，模型改叫 executeCode 又触发审批」的循环。

    命名空间感知（RA-145）：先按 ``.`` 切出命名空间，只对裸工具名归一化，
    永不跨分隔符 mangling —— ``mcp_corp.do_thing`` → ``mcp_corp.doThing``
   （而不是 ``mcpCorp.doThing``，后者什么都匹配不上，是 RA-132 的陷阱）。
    """
    if not name:
        return name
    if "." in name:
        namespace, _, tool_name = name.partition(".")
        return f"{namespace}.{canonical_tool_name(tool_name)}"
    if "_" in name:
        parts = name.split("_")
        camel = parts[0] + "".join(p.capitalize() for p in parts[1:] if p)
        if not camel:
            return name
        return camel[0].lower() + camel[1:]
    if any(ch.isupper() for ch in name[1:]):
        return name[0].lower() + name[1:]
    return name


def required_grant_of(tool: object) -> str:
    """Return the tool's declared grant requirement, or ``""`` when none.

    The ``Tool`` protocol does not carry a grant field; tools that need one
    declare ``required_grant`` as a class attribute.  Absence means the tool
    is grant-agnostic and is governed by ``tools.yaml`` alone.
    """
    return str(getattr(tool, "required_grant", "") or "").strip()


def set_approved_tool_names(names: frozenset[str]) -> None:
    """Set the approved tool set for the current run context (resume task)."""
    _approved_tools_var.set(names)


def get_approved_tool_names() -> frozenset[str]:
    """Return the approved tool set for the current run context (empty = none)."""
    return _approved_tools_var.get()


__all__ = (
    "canonical_tool_name",
    "get_approved_tool_names",
    "required_grant_of",
    "set_approved_tool_names",
)
