"""身份读取与 traits 摘要（ADR-0269 §3 / spec §6.1）。

``load_identity`` 聚合 assistant home 下的 profile.json、IDENTITY.md 与
SOUL.md 的身份/性格/语气章节；``summarize_traits`` 经一次 LLM 调用产出
3–6 个英文风格标签，LLM 不可用时确定性 fallback。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

_PROFILE_JSON = "profile.json"
_IDENTITY_MD = "IDENTITY.md"
_SOUL_MD = "SOUL.md"

# SOUL.md 中参与身份特征的核心语义章节（ADR-0269 §3）。
_SOUL_SECTIONS: tuple[str, ...] = ("身份", "性格", "语气")


def load_identity(home: Path) -> str:
    """聚合 assistant home 的身份文本；文件缺失时跳过对应来源。"""
    parts: list[str] = []
    profile_path = home / _PROFILE_JSON
    if profile_path.exists():
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        parts.append(f"名称: {data.get('name', '')}")
        parts.append(f"简介: {data.get('description', '')}")
        parts.append(f"emoji: {data.get('emoji', '')}")
    identity_path = home / _IDENTITY_MD
    if identity_path.exists():
        parts.append(identity_path.read_text(encoding="utf-8")[:500])
    soul_path = home / _SOUL_MD
    if soul_path.exists():
        text = soul_path.read_text(encoding="utf-8")
        for section in _SOUL_SECTIONS:
            idx = _find_section(text, section)
            if idx >= 0:
                parts.append(text[idx : idx + 300])
    return "\n".join(parts)


def summarize_traits(identity: str, llm: Callable[[str], str] | None) -> str:
    """把身份文本摘要为英文风格标签；无 LLM 时确定性 fallback。"""
    if llm is not None:
        return llm(identity)
    # 确定性 fallback：取前 3 行关键信息（即 name + description + emoji）拼接。
    lines = [line for line in identity.splitlines() if line.strip()][:3]
    return ", ".join(lines) if lines else "default assistant"


def _find_section(text: str, name: str) -> int:
    """返回语义章节标题行的偏移；兼容 ``## 身份`` 与 ``## 🧠 身份`` 写法。"""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        header = stripped.lstrip("#").strip()
        if _strip_emoji(header) == name:
            return text.find(line)
    return -1


def _strip_emoji(text: str) -> str:
    """去掉标题行中的 emoji 与修饰符，仅保留语义文本。"""
    kept: list[str] = []
    for ch in text:
        cp = ord(ch)
        if (
            0x1F000 <= cp <= 0x1FAFF  # emoji 主区
            or 0x2600 <= cp <= 0x27BF  # 杂项符号/装饰
            or cp in (0xFE0F, 0x200D)  # 变体选择符 / 零宽连接符
            or 0x1F3FB <= cp <= 0x1F3FF  # 肤色修饰符
        ):
            continue
        kept.append(ch)
    return "".join(kept).strip()


__all__ = ["load_identity", "summarize_traits"]
