"""``taiyi-cosmokit`` — 1:1 Python port of ``@deepseek-ai/cosmokit``.

The upstream TypeScript package is a zero-dependency utility library that
ships type-name / runtime-type predicates, case / path / property string
helpers, time constants + parsing + formatting helpers, plus binary
(ArrayBuffer / base64 / hex) helpers and a stable deep-clone / deep-equal
pair. The Python port below mirrors each of those surfaces verbatim while
adapting to Python's type system (no ``Symbol``, no implicit ``undefined``,
no non-enumerable properties).

Public surface (re-exports the same names as ``src/index.ts``):

- ``cosmokit.array``     — set / array helpers
- ``cosmokit.types``     — runtime types, binary helpers, clone, deepEqual
- ``cosmokit.misc``      — utility types, object/dict helpers
- ``cosmokit.string``    — case / path / property helpers
- ``cosmokit.time``      — time constants, parsing, formatting

For convenience, the most common names are also re-exported at the
package root.
"""

from cosmokit.array import (
    contain,
    deduplicate,
    difference,
    intersection,
    make_array,
    remove,
    union,
)
from cosmokit.misc import (
    defineProperty,
    filterKeys,
    isNonNullable,
    isNullable,
    isPlainObject,
    mapValues,
    noop,
    omit,
    pick,
    valueMap,
)
from cosmokit.string import (
    camelCase,
    camelize,
    capitalize,
    formatProperty,
    hyphenate,
    paramCase,
    sanitize,
    snakeCase,
    trimSlash,
    uncapitalize,
)
from cosmokit.time import Time
from cosmokit.types import (
    Binary,
    arrayBufferToBase64,
    arrayBufferToHex,
    base64ToArrayBuffer,
    clone,
    deepEqual,
    hexToArrayBuffer,
    is_,
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
