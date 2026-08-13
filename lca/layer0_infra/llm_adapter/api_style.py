"""LLM wire-protocol 风格枚举 —— 零 openai 依赖，供 factory 类型标注使用。"""

from __future__ import annotations

from enum import Enum


class LLMApiStyle(str, Enum):
    """OpenAICompatAdapter 内部 Strategy 选择键。"""

    CHAT_COMPLETIONS = "chat_completions"
    RESPONSES = "responses"
    ANTHROPIC = "anthropic"
