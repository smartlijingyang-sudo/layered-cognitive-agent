"""Top-level DSL builder for ``taiyi-schemastery``.

The TS upstream exports a single ``Schema`` default; the Python port adds
this thin module so callers can write:

    from schemastery import z, refinement

instead of reaching for ``z.transform(inner, predicate, preserve=True)``
when all they want is a predicate guard.

`refinement(inner, predicate)` returns a schema that accepts a value
when it matches ``inner`` AND the predicate returns truthy.
"""

from __future__ import annotations

from collections.abc import Callable as _Callable
from typing import Any

from schemastery.error import ValidationError
from schemastery.schema import Schema

__all__ = ["refinement"]


def refinement(
    inner: Any,
    predicate: _Callable[[Any], bool],
    message: str | None = None,
) -> Schema:
    """Wrap ``inner`` with a predicate guard.

    A ``refinement`` is a ``transform`` whose callback is the predicate —
    when the predicate returns falsy the resolver raises a
    ``ValidationError`` and the value is rejected. By default the error
    message is ``"expected value to satisfy predicate"``; pass ``message``
    to override.
    """

    def _callback(value: Any, _options: Any) -> Any:
        if not predicate(value):
            raise ValidationError(message or "expected value to satisfy predicate", _options)
        return value

    return Schema.transform(inner, _callback, preserve=True)  # type: ignore[attr-defined]
