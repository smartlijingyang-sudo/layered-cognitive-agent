"""Decision 意图形状归一 —— EIP Message Translator / Tolerant Reader。

LLM 自由 JSON 是不可信的外部消息格式。本模块把结构变体（structural
variants）翻译为**规范 Decision 载荷**（Canonical Model），再交给
``SimpleDecisionParser`` 构造领域对象。

管线位置（ADR-0045）::

    JSON 提取 → normalize_intent_shape → action 别名 → Decision → 降级

规则集中在此、声明式优先；禁止在 Body / 前端投影各自发明第二种「猜 JSON」逻辑。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any

from lca.contracts.atoms.enums import ActionType

# 顶层 / 袋内可承载「用户可见正文」的键（顺序即优先级）
_RESPONSE_TEXT_KEYS: tuple[str, ...] = ("response_text", "response", "text")

# LLM 常把参数塞进的嵌套袋
_ARGUMENT_BAG_KEYS: tuple[str, ...] = ("arguments", "args", "parameters")

# 无 ActionRegistry 时，仍把这些 tool_name 视为「伪装成工具的 respond 行动」
_DEFAULT_RESPOND_PSEUDO_TOOLS: frozenset[str] = frozenset(
    {
        ActionType.RESPOND.value,
        "response",
        "answer",
        "reply",
    }
)


def _plain_name(value: object) -> str:
    """把别名/枚举收敛为小写规范名。

    ``str(ActionType.RESPOND)`` 在 str-Enum 上是 ``'ActionType.RESPOND'``，
    不能当字典键用；必须取 ``.value``。
    """
    if isinstance(value, Enum):
        value = value.value
    return str(value).strip().lower()


# 从 arguments 提升到顶层的通用键（伪工具改写时）
_HOIST_KEYS: tuple[str, ...] = (
    "response_text",
    "response",
    "text",
    "rationale",
    "confidence",
    "target_role",
    "subtask",
    "context_refs",
    "context",
    "delegations",
)


def _as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_string(data: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    return None


def _argument_bag(data: Mapping[str, Any]) -> dict[str, Any]:
    for key in _ARGUMENT_BAG_KEYS:
        bag = data.get(key)
        if isinstance(bag, Mapping):
            return dict(bag)
    return {}


def resolve_pseudo_action(
    tool_name: str,
    *,
    resolve_alias: Callable[[str], str] | None = None,
    is_registered: Callable[[str], bool] | None = None,
) -> str | None:
    """若 tool_name 实为行动类型（或别名），返回规范 action_type；否则 None。

    业界对照：OpenAI/Claude 中「回复用户」是文本通道，不是 tool。
    LLM 把 action 写成 tool_name 时，在边界改写而非执行期失败。
    """
    raw = _plain_name(tool_name)
    if not raw:
        return None

    canonical = _plain_name(resolve_alias(raw)) if resolve_alias is not None else raw

    if is_registered is not None:
        if is_registered(canonical) and canonical != ActionType.USE_TOOL.value:
            return canonical
        return None

    if canonical in _DEFAULT_RESPOND_PSEUDO_TOOLS:
        return ActionType.RESPOND.value
    return None


def hoist_response_text(data: Mapping[str, Any], bag: Mapping[str, Any]) -> str | None:
    """规范位置优先，其次 arguments 袋。"""
    top = _first_string(data, _RESPONSE_TEXT_KEYS)
    if top is not None:
        return top
    return _first_string(bag, _RESPONSE_TEXT_KEYS)


def normalize_intent_shape(
    data: Mapping[str, Any],
    *,
    resolve_alias: Callable[[str], str] | None = None,
    is_registered: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """将原始 Decision JSON 字典归一为规范形状（纯函数，不改入参）。

    产出保证：
    - ``action_type`` 为小写字符串（未做词表校验；别名/降级在后续阶段）
    - 用户正文若存在，落在顶层 ``response_text``
    - 伪工具（tool_name 实为 action）已改写为对应 ``action_type``，
      且 ``tool_name`` 清空；原 action 写入 ``_shape_degraded_from``
    """
    out: dict[str, Any] = dict(data)
    bag = _argument_bag(out)
    if bag and not isinstance(out.get("arguments"), Mapping):
        # 统一后续读取口：规范袋键为 arguments
        out["arguments"] = bag

    raw_action = str(out.get("action_type", ActionType.RESPOND.value)).lower().strip()
    out["action_type"] = raw_action

    tool_name_raw = out.get("tool_name") or out.get("tool")
    tool_name = str(tool_name_raw).strip() if tool_name_raw else ""

    response_text = hoist_response_text(out, bag)
    if response_text is not None:
        out["response_text"] = response_text

    # rationale / confidence 可从袋中补全
    if not out.get("rationale") and isinstance(bag.get("rationale"), str):
        out["rationale"] = bag["rationale"]
    if out.get("confidence") is None and bag.get("confidence") is not None:
        out["confidence"] = bag["confidence"]

    pseudo = resolve_pseudo_action(
        tool_name,
        resolve_alias=resolve_alias,
        is_registered=is_registered,
    )
    if pseudo is not None:
        original = raw_action
        out["action_type"] = pseudo
        out["_shape_degraded_from"] = original if original != pseudo else ActionType.USE_TOOL.value
        # 伪工具：行动字段提升后不再保留 tool 调用语义
        out.pop("tool_name", None)
        out.pop("tool", None)
        for key in _HOIST_KEYS:
            if key not in out and key in bag:
                out[key] = bag[key]
        # 再次保证 response_text 规范键
        if response_text is not None:
            out["response_text"] = response_text
        elif (nested := _first_string(bag, _RESPONSE_TEXT_KEYS)) is not None:
            out["response_text"] = nested
        return out

    # use_tool 且无工具名：无法调用 → 形状上视为 respond 候选（与 parser 历史行为对齐）
    if raw_action == ActionType.USE_TOOL.value and not tool_name:
        out["action_type"] = ActionType.RESPOND.value
        out["_shape_degraded_from"] = ActionType.USE_TOOL.value

    return out
