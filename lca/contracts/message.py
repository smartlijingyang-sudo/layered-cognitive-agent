"""Agent 消息模型 —— 多模态 Part 组合，文本为默认形态。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class TextPart:
    text: str
    kind: Literal["text"] = "text"


@dataclass
class DataPart:
    data: dict[str, Any]
    kind: Literal["data"] = "data"


@dataclass
class FileRefPart:
    uri: str
    mime_type: str | None = None
    kind: Literal["file"] = "file"


Part = TextPart | DataPart | FileRefPart


@dataclass
class AgentMessage:
    parts: list[Part]
    role: Literal["user", "agent"] = "user"


def agent_message_text(s: str) -> AgentMessage:
    """构造纯文本 AgentMessage（模块级工厂，符合 ADR-0015）。"""
    return AgentMessage(parts=[TextPart(text=s)])


def agent_message_as_text(msg: AgentMessage) -> str:
    """提取 AgentMessage 中的全部文本 Part。"""
    return "\n".join(p.text for p in msg.parts if isinstance(p, TextPart))
