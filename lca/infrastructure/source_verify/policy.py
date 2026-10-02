"""Verify policy: 来源校验层的介入强度（默认 WARN, 只告警不拦截）."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.cognition.source_verify import VerifyMode


@dataclass(frozen=True, slots=True)
class VerifyPolicy:
    """Run-level switchboard for source-aware verification."""

    mode: VerifyMode = VerifyMode.WARN
    """OFF 关闭校验; WARN 只记录可疑断言（默认, 不改变既有行为）;
    ENFORCE 拦截可疑答案走复核 / 兜底."""

    @classmethod
    def default(cls) -> VerifyPolicy:
        """生产默认: 采集 + 告警, 不拦截."""
        return cls(mode=VerifyMode.WARN)

    @classmethod
    def disabled(cls) -> VerifyPolicy:
        """完全关闭: 只保留来源采集, 跳过校验."""
        return cls(mode=VerifyMode.OFF)

    @classmethod
    def enforcing(cls) -> VerifyPolicy:
        """强制模式: 可疑答案拦截, 需配套复核 / 兜底链路."""
        return cls(mode=VerifyMode.ENFORCE)
