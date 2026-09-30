"""助理人设解析 —— AssistantHome → RoleProfile 三元组（ADR-0187 §3 D3/D12）。

run 期人设注入的唯一入口：``persona_from_home`` 把 Home 的配置面文件
（profile.json / SOUL / USER / goals.yaml）收敛成
``(role, goal, backstory)``，由 run 装配侧覆盖 solo agent 的 RoleProfile。
模型可见通道 = 既有 prompt 模板的 ROLE/GOAL/BACKSTORY 行（不加 section、
不改闭集）。

失败语义：文件缺失/损坏 → 对应字段空串（不抛错；人设降级不阻断 run）。
长度截断：backstory 上限 ``_BACKSTORY_MAX_CHARS``，防 prompt 膨胀。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from lca.infrastructure.assistant.io import read_json_soft
from lca.infrastructure.memory.contextfiles.domain.standing import (
    STANDING_ORDER,
    assemble_standing,
)

_BACKSTORY_MAX_CHARS = 3000
_GOAL_MAX_CHARS = 300


@dataclass(frozen=True)
class AssistantPersona:
    """助理人设三元组（对齐 Agent 构造的 role / goal / backstory）。"""

    role: str = ""
    goal: str = ""
    backstory: str = ""


def persona_from_home(home_path: str) -> AssistantPersona:
    """从 AssistantHome 解析人设；任何文件缺失都降级为空字段。"""
    home = Path(home_path)
    profile = read_json_soft(home / "profile.json")
    name = str(profile.get("name") or "").strip()
    description = str(profile.get("description") or "").strip()

    first_goal = _first_goal_name(home / "goals.yaml")

    goal = description or first_goal
    documents: list[tuple[str, str]] = []
    for file_name in STANDING_ORDER:
        text = _read_text(home / file_name)
        if file_name == "AGENTS.md" and text.strip():
            text = "## 工作约定（AGENTS.md）\n" + text.strip()
        documents.append((file_name, text))
    # 每次装配都重读磁盘。预算先留给 SOUL / USER / MEMORY，再留给工作手册。
    backstory = assemble_standing(documents, budget_chars=_BACKSTORY_MAX_CHARS)
    return AssistantPersona(
        role=name,
        goal=goal[:_GOAL_MAX_CHARS],
        backstory=backstory,
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


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
