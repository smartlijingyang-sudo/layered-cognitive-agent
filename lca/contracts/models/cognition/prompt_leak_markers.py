"""Canonical prompt-leak marker registry (RA-116).

Single named seam shared by prompt producers and the prompt-leak guard. The
invariant "these strings are prompt internals the model must not regurgitate"
lives here and nowhere else:

- producers read the literals they emit into prompts
  (``lca/infrastructure/tool_defer/session.py``,
  ``lca/nodes/think/history/assemble.py``,
  ``lca/plugins/prompts/sections/memory.py``);
- the guard (``lca/nodes/think/decision/parse.py::_guard_prompt_leak``)
  builds its cutoff pattern from :data:`LEAK_MARKER_PATTERNS`.

Renaming a prompt section means editing one place — the guard cannot
silently drift. ``DEFER_CATALOG_HEADER`` has exactly one producing literal:
this module.

Dead markers (``## 认知闭集`` / ``## 核心不变量`` / ``## 系统指令``) were
removed in RA-116: grep proved they appear in no prompt-producing code
(``lca/plugins/prompts/``, ``lca/nodes/think/``, ``bundles/``) — only in the
guard's own old pattern.
"""

from __future__ import annotations

DEFER_CATALOG_HEADER = "Deferred tool namespaces (not yet loaded):"
"""Exact defer-catalog header text. The single producing literal (RA-116)."""

MEMORY_WRITE_RULES_HEADER = "## 记忆写入与写盘铁律"
"""Model-visible memory write-rules section header (memory.py producer)."""

UNRETRIEVED_LABEL = "未检索标注"
"""Uncertainty label producers require on unretrieved memory assertions."""

LEAK_MARKER_PATTERNS: tuple[str, ...] = (
    r"（?未检索标注[：:]",
    r"Deferred tool namespaces",
    r"##\s*记忆写入与写盘铁律",
)
"""Regex fragments the leak guard uses to detect regurgitation.

Each fragment corresponds to a string actually produced into prompts (see
the literals above), in canonical order:

- ``r"（?未检索标注[：:]"`` — ``"- 未检索标注: ..."`` (memory.py)
- ``r"Deferred tool namespaces"`` — :data:`DEFER_CATALOG_HEADER` above
- ``r"##\\s*记忆写入与写盘铁律"`` — :data:`MEMORY_WRITE_RULES_HEADER` above

The guard builds its cutoff pattern as
``r"(\\n*\\s*(?:" + "|".join(LEAK_MARKER_PATTERNS) + r").*)$"``.
"""
