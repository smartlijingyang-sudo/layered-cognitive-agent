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

LCA_UI_MODELS: Final[tuple[str, ...]] = ("solo", "team", "auto", "cordis-creator")
"""LobeHub 模型选择器唯一对外的入口。真实 LLM / agent persona 由 gateway 解析。

- ``solo``    —— 默认独享 agent（web-standard profile 的 default role）
- ``team``    —— LLM casting 自动组队（ADR-0042）
- ``auto``    —— 同 team（显式别名）
- ``cordis-creator`` —— Creator §13.3 自 plugin 创作 persona；同一 web-standard
  profile 上下文，工具集由 cordis-creator role 的 manifest 限定为
  ``cordis_control / file_write / bash`` 三件。
"""

SOLO_MODE_KEY: Final[str] = "solo"
"""Solo 入口：裸模型，零角色概念，不进 MODE_DEFINITIONS（ADR-0052）。"""

CORDIS_CREATOR_MODE_KEY: Final[str] = "cordis-creator"
"""Creator 入口：cordis-creator persona + 创作工具集（single-port 多 persona）。"""

SOLO_ROLE: Final[str] = "助手"
"""Solo agent 的 role 标签 —— 纯展示用，不影响行为（对齐 LobeHub systemRole=''）。"""

CORDIS_CREATOR_ROLE: Final[str] = "cordis-creator"
"""Creator persona 的 role tag；与 profile.cordis-creator.yaml 的 role 字段一致。"""


def resolve_lca_mode(model: str) -> str:
    """Map OpenAI model id → LCA gateway mode ('solo' / 'team' / 'cordis-creator')。"""
    key = model.strip().lower()
    if key in {"team", "auto"}:
        return "team"
    if key == CORDIS_CREATOR_MODE_KEY:
        return CORDIS_CREATOR_MODE_KEY
    return "solo"


def is_cordis_creator_mode(model: str) -> bool:
    """model 是否是 cordis-creator（前端发来 "cordis-creator" 时返回 True）。"""
    return resolve_lca_mode(model) == CORDIS_CREATOR_MODE_KEY


def resolve_agent_role(model: str) -> str:
    """Map model → agent role tag for :class:`Agent` + :class:`RoleProfile`。

    - ``cordis-creator`` → ``cordis-creator``（Creator §13.3 persona）
    - 其它 → ``SOLO_ROLE``（默认助手 persona）
    """
    if is_cordis_creator_mode(model):
        return CORDIS_CREATOR_ROLE
    return SOLO_ROLE
