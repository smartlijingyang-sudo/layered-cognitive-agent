"""Stable import facade for Gateway's OpenAI-compatible housekeeper surface.

Wire encoding, completion service behavior, and HTTP endpoint adaptation are
owned by focused modules.  This module preserves the established imports used by
the application and downstream callers without recreating a second composition
root.
"""

from __future__ import annotations

from gateway.openai_endpoints import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)
from gateway.openai_protocol import LobeHubChatKind, classify_lobehub_chat_request

__all__ = [
    "LobeHubChatKind",
    "chat_completions",
    "classify_lobehub_chat_request",
    "embeddings_create",
    "list_models",
    "responses_create",
]
