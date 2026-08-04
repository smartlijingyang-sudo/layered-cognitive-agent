"""LLM 边界适配：complete/stream 外打 llm.chat span（含 prompt/response 预览）。"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.protocols import LLMAdapter
from lca.contracts.telemetry import (
    ATTR_LATENCY_MS,
    ATTR_MODEL,
    ATTR_OK,
    ATTR_PROMPT_CHARS,
    ATTR_PROMPT_PREVIEW,
    ATTR_RESPONSE_CHARS,
    ATTR_RESPONSE_PREVIEW,
    SpanName,
)
from lca.layer0_infra.observability import span
from lca.layer0_infra.observability.redaction import sanitize, truncate

# Console / JSONL: enough to read task + decision JSON, not full multi-KB dumps.
_LLM_PREVIEW_MAX = 600


def _preview(text: str, *, max_len: int = _LLM_PREVIEW_MAX) -> str:
    return truncate(sanitize(text.replace("\r\n", "\n")), max_len=max_len)


def _model_label(inner: LLMAdapter) -> str:
    model = getattr(inner, "_model", None)
    if isinstance(model, str) and model:
        return model
    name = getattr(inner, "name", None)
    if isinstance(name, str) and name:
        return name
    return type(inner).__name__


class TelemetryLLMAdapter(LLMAdapter):
    """装饰器：不持有后端，使用 ambient Telemetry。"""

    name = "telemetry-llm"

    def __init__(self, inner: LLMAdapter) -> None:
        self._inner = inner
        self.name = f"telemetry({getattr(inner, 'name', type(inner).__name__)})"

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        model = _model_label(self._inner)
        started = time.perf_counter()
        with span(SpanName.LLM_CHAT, **{ATTR_MODEL: model}) as handle:
            handle.attributes[ATTR_PROMPT_CHARS] = len(prompt)
            handle.attributes[ATTR_PROMPT_PREVIEW] = _preview(prompt)
            try:
                text = await self._inner.complete(prompt, **kwargs)
            except Exception:
                handle.attributes[ATTR_OK] = False
                handle.attributes[ATTR_LATENCY_MS] = int((time.perf_counter() - started) * 1000)
                raise
            handle.attributes[ATTR_OK] = True
            handle.attributes[ATTR_LATENCY_MS] = int((time.perf_counter() - started) * 1000)
            handle.attributes[ATTR_RESPONSE_CHARS] = len(text)
            handle.attributes[ATTR_RESPONSE_PREVIEW] = _preview(text)
            return text

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        model = _model_label(self._inner)
        started = time.perf_counter()
        chunks: list[str] = []
        with span(SpanName.LLM_CHAT, **{ATTR_MODEL: model, "stream": True}) as handle:
            handle.attributes[ATTR_PROMPT_CHARS] = len(prompt)
            handle.attributes[ATTR_PROMPT_PREVIEW] = _preview(prompt)
            try:
                async for chunk in self._inner.stream(prompt, **kwargs):
                    chunks.append(chunk)
                    yield chunk
            except Exception:
                handle.attributes[ATTR_OK] = False
                handle.attributes[ATTR_LATENCY_MS] = int((time.perf_counter() - started) * 1000)
                text = "".join(chunks)
                handle.attributes[ATTR_RESPONSE_CHARS] = len(text)
                if text:
                    handle.attributes[ATTR_RESPONSE_PREVIEW] = _preview(text)
                raise
            text = "".join(chunks)
            handle.attributes[ATTR_OK] = True
            handle.attributes[ATTR_LATENCY_MS] = int((time.perf_counter() - started) * 1000)
            handle.attributes[ATTR_RESPONSE_CHARS] = len(text)
            handle.attributes[ATTR_RESPONSE_PREVIEW] = _preview(text)
