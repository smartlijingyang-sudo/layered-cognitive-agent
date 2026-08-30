"""ArtifactClosure Protocol（ADR-0074）。

闭合文本只通过可替换的 ``artifact_closure`` seam 合成。默认实现从 workspace
ledger 读取闭合文本；profile 可通过 ``ctx.provide("artifact_closure", ...)``
注入自定义实现以定制 loop exit 行为。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ArtifactClosure(Protocol):
    """Synthesize artifact closure text for loop exit.

    ADR-0074: expose artifact closure through a pluggable Protocol.
    Default implementation reads from the workspace ledger; profile can replace via
    ``ctx.provide("artifact_closure", ...)`` to customize loop exit behavior.
    """

    def synthesize(self, *, fallback: str = "") -> str | None:
        """Return user-facing closure text, or None if empty."""
        ...


__all__ = ["ArtifactClosure"]
