"""cosmokit.invariant — companion subpackage exposing the public API contract.

This subpackage re-exports the public surface of :mod:`cosmokit` so other
packages in the taiyi workspace can declare a stable dependency on the
contract without coupling to the implementation layout.

1:1 with upstream `vendor/cosmokit/src/invariant.ts` (which in TS is just a
re-export barrel; we mirror that pattern as a Python subpackage).
"""

from __future__ import annotations

from cosmokit import (
    Binary,
    Time,
    arrayBufferToBase64,
    arrayBufferToHex,
    base64ToArrayBuffer,
    camelCase,
    camelize,
    capitalize,
    clone,
    contain,
    deepEqual,
    deduplicate,
    defineProperty,
    difference,
    filterKeys,
    formatProperty,
    hexToArrayBuffer,
    hyphenate,
    intersection,
    is_,
    isNonNullable,
    isNullable,
    isPlainObject,
    make_array,
    mapValues,
    noop,
    omit,
    paramCase,
    pick,
    remove,
    sanitize,
    snakeCase,
    trimSlash,
    uncapitalize,
    union,
    valueMap,
)

__all__ = [
    # array
    "contain",
    "deduplicate",
    "difference",
    "intersection",
    "make_array",
    "remove",
    "union",
    # misc
    "defineProperty",
    "filterKeys",
    "isNonNullable",
    "isNullable",
    "isPlainObject",
    "mapValues",
    "noop",
    "omit",
    "pick",
    "valueMap",
    # string
    "camelCase",
    "camelize",
    "capitalize",
    "formatProperty",
    "hyphenate",
    "paramCase",
    "sanitize",
    "snakeCase",
    "trimSlash",
    "uncapitalize",
    # time
    "Time",
    # types
    "Binary",
    "arrayBufferToBase64",
    "arrayBufferToHex",
    "base64ToArrayBuffer",
    "clone",
    "deepEqual",
    "hexToArrayBuffer",
    "is_",
]