"""OpenAI ChatCompletion chunk line builder (ADR-0099 Phase 1.1).

Produces SSE-formatted bytes (one ``data: ...`` line block per call) that
``StreamingResponse`` of Starlette can flush directly. Conforms to the
public OpenAI ChatCompletion streaming wire so LobeHub's
``model-runtime/openaiCompatibleFactory`` can consume without a custom
patch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OpenAIChatChunkBuilder:
    """Accumulator-agnostic chunk line builder.

    The builder is one-shot per SSE response (one ``streaming_id`` == one
    request). Each public method returns a single SSE block as ``bytes``
    suitable for ``StreamingResponse(iter_bytes)``.
    """

    model: str
    response_id: str = field(default_factory=lambda: f"chatcmpl-lca-{int(time.time() * 1000)}")
    created: int = field(default_factory=lambda: int(time.time()))
    object_type: str = "chat.completion.chunk"

    def _line(self, payload: dict[str, Any]) -> bytes:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()

    def append_content(self, token: str, *, index: int = 0) -> bytes:
        """Emit a single ``delta.content`` chunk line."""
        return self._line(
            {
                "id": self.response_id,
                "object": self.object_type,
                "created": self.created,
                "model": self.model,
                "choices": [
                    {
                        "index": index,
                        "delta": {"role": "assistant", "content": token},
                        "finish_reason": None,
                    }
                ],
            }
        )

    def append_reasoning(self, token: str, *, index: int = 0) -> bytes:
        """Emit a single ``delta.reasoning_content`` chunk line.

        LobeHub ``packages/model-runtime/src/core/streams/openai/openai.ts``
        line 474-528 already maps this field to a LobeHub-native
        ``type: 'reasoning'`` chunk that ``StreamingHandler.handleChunk``
        routes to the existing Reasoning UI (no patch needed).
        """
        return self._line(
            {
                "id": self.response_id,
                "object": self.object_type,
                "created": self.created,
                "model": self.model,
                "choices": [
                    {
                        "index": index,
                        "delta": {"reasoning_content": token},
                        "finish_reason": None,
                    }
                ],
            }
        )

    def start_tool_call(
        self,
        *,
        index: int,
        call_id: str,
        name: str,
        arguments_json: str,
    ) -> bytes:
        """Emit a ``delta.tool_calls`` chunk for the entire tool call payload.

        Arguments are sent in one shot to keep the encoder simple and the
        wire predictable; backend has already completed the tool by the
        time this is emitted, so chunk-streaming adds no value and only
        adds rebuild cost on the client.
        """
        return self._line(
            {
                "id": self.response_id,
                "object": self.object_type,
                "created": self.created,
                "model": self.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": index,
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": arguments_json,
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )

    def tool_call_followup_content(self, message: str, *, index: int = 0) -> bytes:
        """Emit ``delta.content`` after a tool call to carry tool output markdown.

        LobeHub pairs the prior ``tool_calls`` delta with subsequent
        ``role: tool`` content to render a native tool message card; the
        markdown summary here serves as the visible result text.
        """
        return self.append_content(message, index=index)

    def finish_reason(self, reason: str, *, index: int = 0) -> bytes:
        """Emit the terminal ``finish_reason`` chunk (e.g. ``stop``)."""
        return self._line(
            {
                "id": self.response_id,
                "object": self.object_type,
                "created": self.created,
                "model": self.model,
                "choices": [
                    {
                        "index": index,
                        "delta": {},
                        "finish_reason": reason,
                    }
                ],
            }
        )

    def done(self) -> bytes:
        """Emit the OpenAI SSE sentinel — must be the final block."""
        return b"data: [DONE]\n\n"


__all__ = ["OpenAIChatChunkBuilder"]
