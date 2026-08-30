"""LLM infrastructure errors with no configuration or client dependencies."""

from __future__ import annotations


class LLMUnavailableError(RuntimeError):
    """Raised when an LLM credential, endpoint, or compatible API is unavailable."""


__all__ = ["LLMUnavailableError"]
