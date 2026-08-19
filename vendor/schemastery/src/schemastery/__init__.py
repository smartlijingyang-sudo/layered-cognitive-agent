"""`taiyi-schemastery` — 1:1 Python port of `@deepseek-ai/schemastery`.

The public surface re-exports the ``Schema`` class (callable validators with
chainable metadata methods) and the ``ValidationError`` exception. The
``z`` builder is the canonical entry point and is an alias for
``Schema`` itself — every static factory lives on it (``z.string()``,
``z.union([...])``, ``z.object({...})``, …).
"""

from __future__ import annotations

from schemastery.dsl import refinement
from schemastery.error import Issue, Options, ValidationError
from schemastery.schema import Schema, formatters, resolvers

__all__ = [
    "Issue",
    "Options",
    "Schema",
    "ValidationError",
    "formatters",
    "refinement",
    "resolvers",
    "z",
]

z = Schema
"""Top-level DSL builder. Equivalent to the ``default export Schema`` in TS."""
