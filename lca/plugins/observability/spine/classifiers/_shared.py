"""spine exception classifier 共享小件。

``exception_unclass`` / ``exception_builtin`` 原来各有一份函数体相同的
``_current_exception``（从 ``ctx`` 取 ``current_exception`` 的 fail-soft
守卫），收敛到 :func:`current_exception_of`，语义单点定义。
"""

from typing import Any


def current_exception_of(ctx: Any) -> BaseException | None:
    """Return ``ctx.current_exception`` if available, else ``None``.

    The ``FieldProducer`` Protocol types ``ctx`` as ``Any``; the
    spine contract (ADR-0165 / ADR-0165.1 §7.5.2) is that producers
    read ``ctx.current_exception`` during the ``"exception"`` phase.
    Tests and stubs may pass any object exposing the attribute;
    production wiring via ``wrap_instrument`` sets it before the
    producer runs.
    """
    if ctx is None:
        return None
    current = getattr(ctx, "current_exception", None)
    if isinstance(current, BaseException):
        return current
    return None
