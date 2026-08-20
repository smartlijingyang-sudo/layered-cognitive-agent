"""观测 SSE 网关（组合根外薄层，非 lca 包成员）。

`import gateway` only loads this file. Submodules (``gateway.app``,
``gateway.runs.*``, etc.) are imported lazily on first access — that
is Python's native submodule lazy-loading, no custom hook needed.

Why a small `__getattr__` remains
---------------------------------
Python's `from X import Y` does **not** automatically look inside
submodules. To keep the lazy-export ergonomics (``from gateway import
create_app`` works without first forcing `gateway.app` to load), we
re-export two callables from ``gateway.app``. The hook is intentionally
narrow and only forwards by name — it must not re-import through
``gateway`` itself, or we recurse forever (the pre-PR-0 bug).

PR-0 history
------------
The original `__getattr__` also tried to re-export ``app``, which is
both a submodule (``gateway.app``) and a Starlette instance living
inside that submodule. The implementation ``from gateway import app
as _app`` re-invoked this hook and recursed forever. That was the bug.
The fix removes the ``app`` entry from `__all__`; consumers use
``from gateway.app import app`` for the Starlette instance, or
``import gateway.app; gateway.app.app`` for the same.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gateway.app import create_app, get_registry

__all__ = ["create_app", "get_registry"]


def __getattr__(name: str) -> Any:
    """Forward selected names from ``gateway.app`` without recursing."""
    if name not in __all__:
        raise AttributeError(name)
    # `importlib.import_module` bypasses this hook — it imports the
    # submodule by its dotted name rather than asking `gateway` for an
    # attribute. Critical: do NOT write ``from gateway import app``
    # here; that re-enters this hook.
    module = importlib.import_module("gateway.app")
    return getattr(module, name)
