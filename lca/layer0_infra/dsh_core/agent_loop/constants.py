"""Shared agent-loop scheduler defaults.

1:1 port of ``@deepseek-ai/dsh-agent-loop/constants.ts``.
"""

from __future__ import annotations

DEFAULT_MAX_PARALLEL_TOOL_CALLS: int = 10
"""Default maximum in-flight parallel-safe calls per agent step."""
