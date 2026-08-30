"""LobeHub ``call_llm`` turn modes — one LLM invocation per cognitive step."""

from __future__ import annotations

from enum import Enum


class LlmTurnMode(str, Enum):
    """How the Reasoner invokes the LLM for a single step (GeneralChatAgent parity).

    STREAM — default: streamed completion; text and tool_calls come from the same
        response (LobeHub ClientLLMTransport / callLlmFinalizer).
    SUMMARIZE — after a successful ``web_search``: non-stream complete with
        ``tool_choice=none`` so the model synthesizes an answer from tool results.
    """

    STREAM = "stream"
    SUMMARIZE = "summarize"
