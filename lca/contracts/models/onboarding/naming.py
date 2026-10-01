"""Onboarding naming contracts (INV-06, C13 Lineage).

Defines the structured DTO for the naming widget protocol.
All models are strictly frozen with extra fields forbidden.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NamingCandidate(BaseModel):
    """起名候选推荐项。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(description="候选标识，如 cand_athena")
    name: str = Field(description="显示名称，如 Athena")
    vibe: str = Field(description="调性与风格，如 敏锐高效")
    emoji: str = Field(default="🦉", description="角色 Emoji")


class NamingWidgetPayload(BaseModel):
    """起名 Widget 的结构化协议载荷。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str = Field(description="一次性防重放 token")
    assistant_id: str = Field(description="绑定的助理 ID")
    candidates: tuple[NamingCandidate, ...] = Field(description="随机采样的候选名")
    allow_custom: bool = Field(default=True, description="是否允许自定义输入")
    keep_muse: bool = Field(default=False, description="是否保留 Muse 固定选项")
