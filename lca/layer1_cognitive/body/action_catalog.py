"""ActionCatalog —— action_type 的单一事实源。

注册表、Parser 别名、Prompt 文案均由此生成，避免四处硬编码漂移。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.contracts.protocols import SafeExecutor, ToolRegistry, TransportRegistryProtocol
from lca.layer1_cognitive.body.action_handlers import (
    DelegateOperation,
    HandoffOperation,
    RespondOperation,
    UseToolOperation,
)
from lca.layer1_cognitive.body.action_registry import ActionRegistry


@dataclass(frozen=True)
class ActionSpec:
    """一种行动能力的声明。"""

    name: str
    description: str
    aliases: tuple[str, ...] = ()
    """LLM 可能输出的别名；规范名自身也会自动加入 alias map。"""

    executable: bool = True
    """False 表示仅解析/终止语义使用（如 stop），不注册到 ActionRegistry。"""


# 内置行动能力 —— 扩展时优先改这里
BUILTIN_ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="respond",
        description="respond — 直接回复用户（需附带 response_text）",
        aliases=("response", "answer", "reply"),
    ),
    ActionSpec(
        name="use_tool",
        description="use_tool — 调用工具（需附带 tool_name / arguments）",
        aliases=("tool_call", "call_tool"),
    ),
    ActionSpec(
        name="delegate",
        description="delegate — 将子任务委派给队友（需附带 target_role / subtask）",
        aliases=("delegation",),
    ),
    ActionSpec(
        name="handoff",
        description="handoff — 非阻塞移交控制权给其他 Agent",
        aliases=("hand_off",),
    ),
    ActionSpec(
        name="stop",
        description="stop — 任务已完成",
        aliases=(),
        executable=False,
    ),
    ActionSpec(
        name="ask_human",
        description="ask_human — 请求人工介入",
        aliases=("hitl",),
        executable=False,
    ),
)


def build_action_alias_map(specs: Sequence[ActionSpec] = BUILTIN_ACTION_SPECS) -> dict[str, str]:
    """规范名 + 别名 → 规范名。"""
    mapping: dict[str, str] = {}
    for spec in specs:
        mapping[spec.name] = spec.name
        for alias in spec.aliases:
            mapping[alias] = spec.name
    return mapping


def format_allowed_actions_desc(
    allowed_names: Sequence[str],
    specs: Sequence[ActionSpec] = BUILTIN_ACTION_SPECS,
) -> str:
    """按已注册 action 列表生成 Prompt 段落。"""
    by_name = {s.name: s for s in specs}
    lines: list[str] = []
    for i, name in enumerate(allowed_names):
        spec = by_name.get(name)
        desc = spec.description if spec is not None else f"{name} — (自定义)"
        lines.append(f"{i + 1}. {desc}")
    return "\n".join(lines)


def build_default_action_registry(
    tool_registry: ToolRegistry,
    safe_executor: SafeExecutor,
    transport_registry: TransportRegistryProtocol,
) -> ActionRegistry:
    """构建包含所有可执行内置 ActionOperation 的默认注册表。"""
    registry = ActionRegistry()
    registry.register("respond", RespondOperation())
    registry.register("use_tool", UseToolOperation(tool_registry, safe_executor))
    registry.register("delegate", DelegateOperation(transport_registry))
    registry.register("handoff", HandoffOperation(transport_registry))
    return registry
