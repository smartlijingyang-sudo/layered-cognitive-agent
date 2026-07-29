"""Agent 消息模型 —— 多模态 Part 组合，文本为默认形态。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.enums import MessageKind, MessageRole


@dataclass
class TextPart:
    text: str
    kind: MessageKind = MessageKind.TEXT


@dataclass
class DataPart:
    data: dict[str, Any]
    kind: MessageKind = MessageKind.DATA


@dataclass
class FileRefPart:
    uri: str
    mime_type: str | None = None
    kind: MessageKind = MessageKind.FILE


Part = TextPart | DataPart | FileRefPart


@dataclass
class AgentMessage:
    parts: list[Part]
    role: MessageRole = MessageRole.USER


def agent_message_text(s: str) -> AgentMessage:
    """构造纯文本 AgentMessage（模块级工厂，符合 ADR-0015）。"""
    return AgentMessage(parts=[TextPart(text=s)])


def agent_message_as_text(msg: AgentMessage) -> str:
    """提取 AgentMessage 中的全部文本 Part。"""
    return "\n".join(p.text for p in msg.parts if isinstance(p, TextPart))
