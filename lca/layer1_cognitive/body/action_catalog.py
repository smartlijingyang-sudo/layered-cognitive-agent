"""ActionCatalog —— action_type 的单一事实源。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.contracts.action import Action
from lca.contracts.enums import ActionType
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
    """Declarative specification of a built-in action type.

    Defines the canonical name, human-readable description, accepted aliases,
    and whether the action is directly executable (vs. a control signal like
    ``stop`` or ``ask_human``).
    """

    name: str
    description: str
    aliases: tuple[str, ...] = ()
    executable: bool = True


BUILTIN_ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name=ActionType.RESPOND,
        description="respond — 直接回复用户（需附带 response_text）",
        aliases=("response", "answer", "reply"),
    ),
    ActionSpec(
        name=ActionType.USE_TOOL,
        description="use_tool — 调用工具（需附带 tool_name / arguments）",
        aliases=("tool_call", "call_tool"),
    ),
    ActionSpec(
        name=ActionType.DELEGATE,
        description="delegate — 将子任务委派给队友（需附带 target_role / subtask）",
        aliases=("delegation",),
    ),
    ActionSpec(
        name=ActionType.HANDOFF,
        description="handoff — 非阻塞移交控制权给其他 Agent",
        aliases=("hand_off",),
    ),
    ActionSpec(name=ActionType.STOP, description="stop — 任务已完成", aliases=(), executable=False),
    ActionSpec(
        name=ActionType.ASK_HUMAN,
        description="ask_human — 请求人工介入",
        aliases=("hitl",),
        executable=False,
    ),
)


def build_action_alias_map(specs: Sequence[ActionSpec] = BUILTIN_ACTION_SPECS) -> dict[str, str]:
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
    by_name = {s.name: s for s in specs}
    lines: list[str] = []
    for i, name in enumerate(allowed_names):
        spec = by_name.get(name)
        desc = spec.description if spec is not None else f"{name} — (自定义)"
        lines.append(f"{i + 1}. {desc}")
    return "\n".join(lines)


def _operation_for(
    name: str,
    tool_registry: ToolRegistry,
    safe_executor: SafeExecutor,
    transport_registry: TransportRegistryProtocol,
) -> Action | None:
    if name == ActionType.RESPOND:
        return RespondOperation()
    if name == ActionType.USE_TOOL:
        return UseToolOperation(tool_registry, safe_executor)
    if name == ActionType.DELEGATE:
        return DelegateOperation(transport_registry)
    if name == ActionType.HANDOFF:
        return HandoffOperation(transport_registry)
    return None


def build_default_action_registry(
    tool_registry: ToolRegistry,
    safe_executor: SafeExecutor,
    transport_registry: TransportRegistryProtocol,
) -> ActionRegistry:
    registry = ActionRegistry()
    for spec in BUILTIN_ACTION_SPECS:
        if not spec.executable:
            continue
        op = _operation_for(spec.name, tool_registry, safe_executor, transport_registry)
        if op is None:
            continue
        registry.register(spec.name, op)
        for alias in spec.aliases:
            registry.register_alias(alias, spec.name)
    return registry
