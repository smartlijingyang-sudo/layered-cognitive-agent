"""标准适配器使用的诊断事件发射辅助函数。"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.observability.diagnostic import DiagnosticCategory
from lca.layer0_infra.observability.facade import record_runtime


def record_llm_completion(
    *,
    model: str,
    stream: bool,
    ok: bool,
    prompt: str,
    prompt_tokens: int,
    response_text: str,
    completion_tokens: int,
    latency_ms: int,
) -> None:
    """写入 LLM 完成诊断；Journal 事实仍由调用方独立发射。"""
    record_runtime(
        DiagnosticCategory.LLM,
        "llm.complete",
        plugin="telemetry.llm",
        attributes={
            "model": model,
            "stream": stream,
            "ok": ok,
            "prompt_preview": prompt,
            "prompt_tokens": prompt_tokens,
        },
        output={
            "response_preview": response_text,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
        },
    )


def record_memory_operation(
    operation: str,
    inner: object,
    *,
    attributes: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
) -> None:
    """写入记忆边界的轻量诊断。"""
    record_runtime(
        DiagnosticCategory.MEMORY,
        operation,
        plugin=type(inner).__name__,
        attributes=attributes,
        output=output,
    )


__all__ = ["record_llm_completion", "record_memory_operation"]
