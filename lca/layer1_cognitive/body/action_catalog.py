"""ActionCatalog —— action_type 的单一事实源。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.contracts.atoms.enums import ActionType


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


def format_allowed_actions_desc(
    allowed_names: Sequence[str],
    specs: Sequence[ActionSpec] = BUILTIN_ACTION_SPECS,
) -> str:
    """Format the action names already permitted by compiled authority."""
    by_name = {spec.name: spec for spec in specs}
    lines: list[str] = []
    for index, name in enumerate(allowed_names):
        spec = by_name.get(name)
        description = spec.description if spec is not None else f"{name} — (自定义)"
        lines.append(f"{index + 1}. {description}")
    return "\n".join(lines)


__all__ = ["BUILTIN_ACTION_SPECS", "ActionSpec", "format_allowed_actions_desc"]
