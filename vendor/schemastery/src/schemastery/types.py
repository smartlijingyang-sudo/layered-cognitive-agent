"""Primitive schema factories.

This module re-exports the primitive schema constructors (``string``,
``number``, ``boolean``, ``const``, ``natural``, ``percent``, ``date``,
``reg_exp``, ``array_buffer``, ``bitset``, ``function``, ``is_``, ``any``,
``never``) from :mod:`schemastery.schema` so callers can write
``from schemastery.types import string`` without dragging in the rest of
the resolver/formatter machinery.

The TS upstream does not split these into a separate module — they're
all defined on the ``Schema`` constructor in ``index.ts``. Splitting them
out here keeps the Python module structure aligned with the spec table
in ``docs/superpowers/specs/.../1to1-design.md`` §3 / §5.
"""

from __future__ import annotations

from schemastery.schema import (
    _any_factory,
    _array_buffer_factory,
    _bitset_factory,
    _boolean_factory,
    _const_factory,
    _date_factory,
    _function_factory,
    _is_factory,
    _natural_factory,
    _never_factory,
    _number_factory,
    _percent_factory,
    _reg_exp_factory,
    _string_factory,
)

__all__ = [
    "any_",
    "array_buffer",
    "bitset",
    "boolean",
    "const",
    "date",
    "function",
    "is_",
    "natural",
    "never",
    "number",
    "percent",
    "reg_exp",
    "string",
]

# ``any`` is a Python builtin — alias the factory under a trailing underscore
# for the type module. The ``Schema.any`` static method keeps the TS spelling.
any_ = _any_factory
array_buffer = _array_buffer_factory
bitset = _bitset_factory
boolean = _boolean_factory
const = _const_factory
date = _date_factory
function = _function_factory
is_ = _is_factory
natural = _natural_factory
never = _never_factory
number = _number_factory
percent = _percent_factory
reg_exp = _reg_exp_factory
string = _string_factory
