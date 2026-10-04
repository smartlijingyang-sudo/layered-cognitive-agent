"""助理人设解析 —— AssistantHome → RoleProfile 三元组（ADR-0187 §3 D3/D12）。

run 期人设注入的唯一入口：``persona_from_home`` 把 Home 的配置面文件
（profile.json / SOUL / USER / goals.yaml）收敛成
``(role, goal, backstory)``，由 run 装配侧覆盖 solo agent 的 RoleProfile。
模型可见通道 = 既有 prompt 模板的 ROLE/GOAL/BACKSTORY 行（不加 section、
不改闭集）。

失败语义：文件缺失/损坏 → 对应字段空串（不抛错；人设降级不阻断 run）。
backstory 预算、常驻文件名单和工作手册标题来自上下文布局文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from lca.infrastructure.assistant.io import read_json_soft
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.domain.standing import assemble_standing
from lca.infrastructure.memory.contextfiles.service.assembly import (
    read_standing_documents,
)

_GOAL_MAX_CHARS = 300


@dataclass(frozen=True)
class AssistantPersona:
    """助理人设三元组（对齐 Agent 构造的 role / goal / backstory）。"""

    role: str = ""
    goal: str = ""
    backstory: str = ""


def persona_from_home(
    home_path: str,
    *,
    platform_root: str | Path | None = None,
) -> AssistantPersona:
    """从 AssistantHome 解析人设；任何文件缺失都降级为空字段。"""
    home = Path(home_path)
    profile = read_json_soft(home / "profile.json")
    name = str(profile.get("name") or "").strip()
    description = str(profile.get("description") or "").strip()

    first_goal = _first_goal_name(home / "goals.yaml")

    goal = description or first_goal
    layout = layout_for_home(home_path)
    documents = read_standing_documents(home_path, layout, platform_root=platform_root)
    backstory = assemble_standing(
        documents,
        budget_chars=layout.backstory_budget_chars,
        order=[name for name, _ in documents],
        platform_files=layout.platform_files,
        protected_files=layout.protected_files,
        protected_budget_chars=layout.protected_budget_chars,
    )
    return AssistantPersona(
        role=name,
        goal=goal[:_GOAL_MAX_CHARS],
        backstory=backstory,
    )


def _first_goal_name(goals_path: Path) -> str:
    try:
        data = yaml.safe_load(goals_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return ""
    goals = data.get("goals") if isinstance(data, dict) else None
    if isinstance(goals, list) and goals:
        first = goals[0]
        if isinstance(first, dict):
            return str(first.get("name") or "").strip()
    return ""


__all__ = ["AssistantPersona", "persona_from_home"]
