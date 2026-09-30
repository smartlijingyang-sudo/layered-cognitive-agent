"""内容指纹 —— 跨写路径的语义事实去重（ADR-0247 回归）。

把同一事实的不同措辞（标签前缀、引号、称呼变体）收敛为同一指纹，
供 ``AssistantMemory`` 与迁移去重共用，避免两处实现漂移。
"""

from __future__ import annotations

import re

# 内容指纹前缀标签：这些标签后的剩余部分是事实核心，跨路径去重时忽略。
_FINGERPRINT_LABELS: frozenset[str] = frozenset(
    {
        "用户身份",
        "用户偏好",
        "用户称呼偏好",
        "称呼偏好",
        "称呼",
        "身份",
        "偏好",
        "事实",
    }
)

# 称呼类变体：不同措辞表达同一语义（叫他X / 叫我X / 称呼用户为X / 希望被称呼为X），
# 归一到 ``称呼X``，让跨写入路径（memory_add vs 自动提取）能收敛。
_ADDRESS_VARIANTS_RE = re.compile(r"^(?:叫他|叫我|称呼用户为|希望被称呼为|称呼我为|称呼为)")


def content_fingerprint(content: str) -> str:
    """结构化事实的内容指纹：去引号、去常见标签前缀、称呼变体归一、去空白。

    用于 store 边界的内容级幂等（ADR-0247 回归）。例如：
    - ``称呼偏好：称呼用户为"老板"`` 与 ``用户偏好：称呼用户为老板``
      都收敛为 ``称呼老板``。
    - ``用户称呼偏好：叫他「老板」`` 与 ``用户偏好：希望被称呼为老板``
      都收敛为 ``称呼老板``。
    """
    normalized = content
    for ch in "\"'「」『』“”‘’":
        normalized = normalized.replace(ch, "")
    if "：" in normalized:
        label, _, rest = normalized.partition("：")
        if label.strip() in _FINGERPRINT_LABELS:
            normalized = rest
    normalized = _ADDRESS_VARIANTS_RE.sub("称呼", normalized)
    return "".join(normalized.split())


__all__ = ["content_fingerprint"]
