"""Gateway 协作模式目录 —— UI 与生产组队的单一事实源（ADR-0052）。

Solo/Team 分治：solo 是裸模型（零角色概念，对齐 LobeHub 默认 agent），
team 走 LLM casting（ADR-0042）。本模块只定义 team 模式的 UI 元数据；
solo 不进 MODE_DEFINITIONS，由 run_executor 直接构造。

测试 CLI 探针（``tests/harness/modes.py``）保留 Alice/Bob 剧本用于确定性探针；
本模块定义面向真实用户的产品文案。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ModeDefinition:
    """一种协作模式的 UI 元数据。"""

    key: str
    help_text: str
    example_prompts: tuple[str, ...]


MODE_DEFINITIONS: Final[dict[str, ModeDefinition]] = {
    "team": ModeDefinition(
        key="team",
        help_text="团队 · 系统按任务自动组队和分工",
        example_prompts=(
            "给新功能写发布文案并评估技术风险",
            "制定季度产品路线图的关键里程碑",
            "从效率、协作、文化三个角度分析远程办公",
            "是否应在本周发布灰度版本？",
        ),
    ),
}

ALL_MODES: Final[tuple[str, ...]] = tuple(MODE_DEFINITIONS.keys())

MODE_HELP: Final[dict[str, str]] = {
    key: definition.help_text for key, definition in MODE_DEFINITIONS.items()
}

EXAMPLE_PROMPTS: Final[dict[str, tuple[str, ...]]] = {
    key: definition.example_prompts for key, definition in MODE_DEFINITIONS.items()
}

DEFAULT_MODE: Final[str] = "solo"

SOLO_MODE_KEY: Final[str] = "solo"
"""Solo 入口：裸模型，零角色概念，不进 MODE_DEFINITIONS（ADR-0052）。"""

SOLO_ROLE: Final[str] = "助手"
"""Solo agent 的 role 标签 —— 纯展示用，不影响行为（对齐 LobeHub systemRole=''）。"""
