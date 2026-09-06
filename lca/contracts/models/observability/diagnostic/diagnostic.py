"""运行诊断事件契约（ADR-0063）。

``DiagnosticEvent`` 是 run-scoped 的可观测诊断封套，不是 Journal 事实。
它服务于调试、解释与外部观测投影；恢复、重放、状态归约必须只读取
Journal。因此本模型保持小而稳定：关联骨架、操作身份、结果状态和经过
统一策略处理的输入/输出属性。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DiagnosticCategory(str, Enum):
    """诊断事件的对象域；用于跨插件与跨后端的稳定过滤。"""

    AGENT = "agent"
    PLUGIN = "plugin"
    HOOK = "hook"
    LLM = "llm"
    TOOL = "tool"
    MEMORY = "memory"
    TRANSPORT = "transport"
    INFRA = "infra"
    JOURNAL = "journal"


class DiagnosticStatus(str, Enum):
    """一次诊断操作的终态。"""

    INFO = "info"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class DiagnosticEvent:
    """可追加、可投影的 run-scoped 诊断记录。

    ``causation_refs`` 以 ``journal:<seq>`` 等稳定引用把诊断行连回事实流，
    而不会把诊断行变成事实流的一部分。
    """

    schema: str = "lca.diagnostic.v1"
    seq: int = 0
    ts: float = 0.0
    run_id: str = ""
    trace_id: str = ""
    parent_run_id: str | None = None
    delegation_id: str | None = None
    actor: str = ""
    step: int | None = None
    category: DiagnosticCategory = DiagnosticCategory.INFRA
    operation: str = ""
    plugin: str = ""
    status: DiagnosticStatus = DiagnosticStatus.INFO
    duration_ms: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    error_message: str = ""
    causation_refs: tuple[str, ...] = ()


__all__ = ["DiagnosticCategory", "DiagnosticEvent", "DiagnosticStatus"]
