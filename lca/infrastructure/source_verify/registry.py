"""Per-run source registry —— 本轮 agent 见过的所有证据来源的登记簿.

ProvenanceGuard 的第一原则: 绝不把证据塌缩成一个匿名上下文.
来源身份（source_id）从工具输出产生的一刻起, 一路带到校验裁决.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, UTC
from typing import Any

from lca.contracts.models.cognition.source_verify import SourceKind, SourceRef


@dataclass
class _SourceEntry:
    ref: SourceRef
    content: str


class SourceRegistry:
    """登记本轮所有模型可见的证据来源."""

    def __init__(self) -> None:
        self._entries: dict[str, _SourceEntry] = {}
        self._seq = 0

    def register_tool_result(
        self,
        *,
        call_id: str,
        tool_name: str,
        content: str,
        label: str = "",
    ) -> SourceRef:
        """登记一条工具调用输出. source_id 稳定为 ``tool:<call_id>``."""
        return self.register(
            kind=SourceKind.TOOL,
            label=label or tool_name,
            content=content,
            tool_name=tool_name,
            call_id=call_id,
            source_id=f"tool:{call_id}",
        )

    def register(
        self,
        *,
        kind: SourceKind,
        label: str,
        content: str,
        tool_name: str | None = None,
        call_id: str | None = None,
        source_id: str | None = None,
    ) -> SourceRef:
        """登记一条任意来源的证据, 返回其 SourceRef."""
        if source_id is None:
            self._seq += 1
            source_id = f"{kind.value}:{self._seq}"
        ref = SourceRef(
            source_id=source_id,
            kind=kind,
            label=label,
            tool_name=tool_name,
            call_id=call_id,
            captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._entries[source_id] = _SourceEntry(ref=ref, content=content)
        return ref

    def get(self, source_id: str) -> tuple[SourceRef, str] | None:
        """取回 (SourceRef, 原文内容); 不存在返回 None."""
        entry = self._entries.get(source_id)
        if entry is None:
            return None
        return entry.ref, entry.content

    def resolve_label(self, label: str) -> str | None:
        """把"根据X"里的 X 解析成 source_id; 找不到返回 None."""
        needle = label.strip()
        for sid, entry in self._entries.items():
            if entry.ref.label == needle or entry.ref.tool_name == needle:
                return sid
        return None

    def source_ids(self) -> tuple[str, ...]:
        return tuple(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)


def source_marker(source_id: str) -> str:
    """模型可见的工具结果首行标记 —— 模型引用来源时用的稳定 ID."""
    return f"[source:{source_id}]"


_REGISTRY_ATTR = "_lca_source_registry"


def get_registry(runtime: Any | None) -> SourceRegistry | None:
    """从 run-scoped runtime 上取回 SourceRegistry；没有返回 None."""
    if runtime is None:
        return None
    try:
        if isinstance(runtime, dict):
            v = runtime.get(_REGISTRY_ATTR)
        else:
            v = getattr(runtime, _REGISTRY_ATTR, None)
    except Exception:
        return None
    return v if isinstance(v, SourceRegistry) else None


def ensure_registry(runtime: Any | None) -> SourceRegistry:
    """取回或创建挂在 runtime 上的 SourceRegistry.

    runtime 为 None（legacy harness）或不可写时，返回一个临时的、
    挂不上去的 registry —— 调用方仍可正常登记，本轮校验只是取不到它。
    """
    reg = get_registry(runtime)
    if reg is not None:
        return reg
    reg = SourceRegistry()
    if runtime is not None:
        try:
            if isinstance(runtime, dict):
                runtime[_REGISTRY_ATTR] = reg
            else:
                setattr(runtime, _REGISTRY_ATTR, reg)
        except Exception:
            pass
    return reg
