"""Per-run source registry —— 本轮 agent 见过的所有证据来源的登记簿.

ProvenanceGuard 的第一原则: 绝不把证据塌缩成一个匿名上下文.
来源身份（source_id）从工具输出产生的一刻起, 一路带到校验裁决.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


def source_marker(source_id: str) -> str:
    """模型可见的工具结果首行标记 —— 模型引用来源时用的稳定 ID."""
    return f"[source:{source_id}]"


_SOURCE_REGISTRY_CAPABILITY = "source_registry"


def get_registry(runtime: Any | None) -> SourceRegistry | None:
    """从 runtime 的显式 ``source_registry`` capability 取回登记表.

    ``AgentState`` 是 reducer-owned 数据投影, 不承载可变运行时服务. 生产图的
    ``NodeRuntimeView`` 与 ``RuntimePhaseCapabilities`` 均通过 ``get`` 暴露该
    capability; 普通映射/legacy runtime 属性只用于轻量测试与兼容 harness.
    """
    if isinstance(runtime, SourceRegistry):
        return runtime
    if runtime is None:
        return None

    getter = getattr(runtime, "get", None)
    if callable(getter):
        try:
            value = getter(_SOURCE_REGISTRY_CAPABILITY)
        except (KeyError, AttributeError, TypeError):
            value = None
        if isinstance(value, SourceRegistry):
            return value

    value = getattr(runtime, _SOURCE_REGISTRY_CAPABILITY, None)
    return value if isinstance(value, SourceRegistry) else None


def ensure_registry(runtime: Any | None) -> SourceRegistry:
    """取回或在可写 legacy runtime 上创建 registry, 从不修改 AgentState.

    正式运行时由 run-scoped ``source_registry`` capability 提供同一实例, 供
    effect 节点登记和最终答案校验共用。没有该 capability 的 legacy harness
    会得到一个临时 registry; 只读 runtime view 不会被写入。
    """
    registry = get_registry(runtime)
    if registry is not None:
        return registry

    registry = SourceRegistry()
    if runtime is None:
        return registry
    try:
        if isinstance(runtime, MutableMapping):
            runtime[_SOURCE_REGISTRY_CAPABILITY] = registry
        else:
            setattr(runtime, _SOURCE_REGISTRY_CAPABILITY, registry)
    except (AttributeError, TypeError):
        # NodeRuntimeView is deliberately read-only. Production wiring must
        # provide the registry through RuntimePhaseCapabilities instead.
        pass
    return registry
