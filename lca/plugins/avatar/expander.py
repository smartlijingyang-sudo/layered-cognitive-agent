"""通用头像生图提示词扩写器（PromptExpander，消除硬编码反模式）。

本模块提供生图提示词生成的机制化解法：
1. ``PromptExpander`` 协议定义统一的异步扩写接口；
2. ``RulePromptExpander``：纯规则通用前缀剥离与结构化肖像模板生成，
   绝对不包含任何特例人物/实体名单；
3. ``LlmPromptExpander``：通用 1-shot 提示词工程转换器，可接入轻量 LLM
   动态理解任意现实/虚构主体，并在失败时自愈回退到 RulePromptExpander。
"""

from __future__ import annotations

import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

_TRANSITION_VERB_REGEX = re.compile(
    r"^.*?(?:改成|换成|变成|设置为|更新为|调整为|修改为|做成|设为|换做)[：:\s]*(.+)$",
    re.IGNORECASE | re.DOTALL,
)

_LEADING_REQUEST_VERB_REGEX = re.compile(
    r"^(?:我想|请帮我|麻烦帮我|麻烦|请|帮我|希望)?(?:做个|画一个|画个|来个|要一个|想要一个|想要|换个|换一件|换套|换|改)[：:\s]*(.+)$",
    re.IGNORECASE | re.DOTALL,
)

_LEADING_PREFIX_REGEX = re.compile(
    r"^(?:我想|请帮我|麻烦帮我|麻烦|请|帮我|希望)?(?:修改|更改|调整|更换)?(?:你的)?(?:形象|头像|装扮|外观|风格)?(?:：|:|，|,|\s)*",
    re.IGNORECASE,
)

_LEADING_ARTICLE_REGEX = re.compile(r"^(?:一个|一名|一只|一位|一套|一件|一种)\s*")
_TRAILING_PUNCTUATION_REGEX = re.compile(r"[。！!？?~～,，;；:\s]+$")


@runtime_checkable
class PromptExpander(Protocol):
    """通用头像生图提示词扩写器契约。"""

    async def expand(self, user_request: str) -> str:
        """将用户自然语言/口语请求转换为生图模型可理解的视觉描述。"""
        ...


class RulePromptExpander:
    """确定性语法规则扩写器（零特例硬编码）。

    通用剥离长句中的口语化指令前缀，提取主体核心描述，
    并组装成符合下游视觉模型审美规范的高清头像模板。
    """

    def clean_subject(self, user_request: str) -> str:
        """剥离通用对话指令前缀与末尾标点，提取核心主体词。"""
        text = user_request.strip()
        # 1. 优先捕获转移目标动词后的主体（如“改成：XXX”、“换成：XXX”）
        m_trans = _TRANSITION_VERB_REGEX.match(text)
        if m_trans:
            text = m_trans.group(1).strip()
        elif m_req := _LEADING_REQUEST_VERB_REGEX.match(text):
            # 2. 捕获请求动词后的主体（如“做个XXX”、“想要XXX”）
            text = m_req.group(1).strip()
        else:
            # 3. 剥离通用前置短语（如“我想修改头像为：”）
            text = _LEADING_PREFIX_REGEX.sub("", text).strip()

        # 4. 剥离量词前缀（如“一个/一只”）
        text = _LEADING_ARTICLE_REGEX.sub("", text).strip()
        # 5. 去掉末尾语气标点与多余空白
        text = _TRAILING_PUNCTUATION_REGEX.sub("", text).strip()
        return text

    async def expand(self, user_request: str) -> str:
        subject = self.clean_subject(user_request)
        if not subject:
            return (
                "Close-up avatar portrait, highly detailed character design, "
                "professional studio lighting, centered composition, high quality"
            )
        return (
            f"Close-up avatar portrait of {subject}, highly detailed character design, "
            f"professional studio lighting, centered composition, high quality"
        )


class LlmPromptExpander:
    """基于轻量 LLM 的通用视觉提示词工程转换器。

    调用通识大模型将任意自然语言请求扩写为生图模型专用的英文 Prompt。
    支持同步或异步 Callable，并在 LLM 调用异常时优雅降级至 RulePromptExpander。
    """

    _SYSTEM_INSTRUCTION = (
        "You are an expert avatar prompt engineer. Convert the user's avatar request "
        "into a detailed, high-quality text-to-image prompt (subject appearance, distinctive "
        "facial traits, attire, lighting, style, centered composition). Output only the English prompt."
    )

    def __init__(
        self,
        llm: Callable[[str], Awaitable[str] | str],
        fallback: PromptExpander | None = None,
    ) -> None:
        self._llm = llm
        self._fallback = fallback or RulePromptExpander()

    async def expand(self, user_request: str) -> str:
        try:
            res = self._llm(user_request)
            if inspect.isawaitable(res):
                res = await res
            expanded = str(res).strip()
            if expanded:
                return expanded
        except Exception as exc:
            logger.warning("LlmPromptExpander failed, falling back to rule expander: %s", exc)
        return await self._fallback.expand(user_request)


__all__ = ["LlmPromptExpander", "PromptExpander", "RulePromptExpander"]
