"""String case, path, and property formatting helpers.

1:1 Python port of ``@deepseek-ai/cosmokit/src/string.ts``.

Notes on translation:

- The TS ``tokenize`` uses ``charCodeAt`` arithmetic on the entire string;
  the Python port keeps the same byte-by-byte state machine and converts
  back to ``chr`` at the end.
- ``formatProperty``'s bracket branch uses ``json.dumps`` so numeric /
  string / whitespace / quoted keys all encode as the JS-equivalent JSON
  literal.
"""

import json
import re
from typing import Any

__all__ = [
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
]


# ---------------------------------------------------------------------------
# Capitalize / uncapitalize
# ---------------------------------------------------------------------------


def capitalize(source: str) -> str:
    """Uppercase the first character of ``source``."""
    if not source:
        return source
    return source[0].upper() + source[1:]


def uncapitalize(source: str) -> str:
    """Lowercase the first character of ``source``."""
    if not source:
        return source
    return source[0].lower() + source[1:]


# ---------------------------------------------------------------------------
# camelCase
# ---------------------------------------------------------------------------


_CAMEL_PATTERN = re.compile(r"[_-][a-z]")


def camelCase(source: str) -> str:
    """Convert dash / underscore delimited text to camelCase.

    Mirrors ``source.replace(/[_-][a-z]/g, str => str.slice(1).toUpperCase())``.
    """
    return _CAMEL_PATTERN.sub(lambda m: m.group(0)[1].upper(), source)


# Runtime alias matching the TS export.
camelize = camelCase


# ---------------------------------------------------------------------------
# tokenize / paramCase / snakeCase
# ---------------------------------------------------------------------------

# State machine states mirror the TS ``const enum State { DELIM, UPPER, LOWER }``.
_DELIM, _UPPER, _LOWER = 0, 1, 2


def _tokenize(source: str, delimiters: tuple[int, ...], delimiter: int) -> str:
    """Faithful port of the TS ``tokenize`` state machine.

    Builds a list of character codes while walking a 4-state FSM, then joins
    back to a string.
    """
    out: list[int] = []
    state = _DELIM
    for i, ch in enumerate(source):
        code = ord(ch)
        if 65 <= code <= 90:  # uppercase A-Z
            if state == _UPPER:
                # ``[_-][a-z]`` style acronym boundary: UPPER followed by lower.
                next_code = ord(source[i + 1]) if i + 1 < len(source) else 0
                if 97 <= next_code <= 122:
                    out.append(delimiter)
                out.append(code + 32)
            else:
                if state != _DELIM:
                    out.append(delimiter)
                out.append(code + 32)
            state = _UPPER
        elif 97 <= code <= 122:  # lowercase a-z
            out.append(code)
            state = _LOWER
        elif code in delimiters:
            if state != _DELIM:
                out.append(delimiter)
            state = _DELIM
        else:
            out.append(code)
    return "".join(chr(c) for c in out)


def paramCase(source: str) -> str:
    """Convert text to dash-delimited ``param-case``.

    Mirrors ``tokenize(source, [45, 95], 45)``.
    """
    return _tokenize(source, (45, 95), 45)


def snakeCase(source: str) -> str:
    """Convert text to underscore-delimited ``snake_case``.

    Mirrors ``tokenize(source, [45, 95], 95)``.
    """
    return _tokenize(source, (45, 95), 95)


# Runtime alias matching the TS ``hyphenate`` export.
hyphenate = paramCase


# ---------------------------------------------------------------------------
# formatProperty
# ---------------------------------------------------------------------------

_VALID_JS_IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")


def formatProperty(key: Any) -> str:
    """Return a JavaScript member-access suffix for ``key``.

    - valid JS identifier → ``.key``
    - string with invalid identifier chars → ``[<json-string>]`` with quotes
    - non-string → ``[toString]`` without quotes
    """
    if not isinstance(key, str):
        return f"[{key}]"
    if _VALID_JS_IDENT.match(key):
        return f".{key}"
    return f"[{json.dumps(key)}]"


# ---------------------------------------------------------------------------
# trimSlash / sanitize
# ---------------------------------------------------------------------------

_TRAILING_SLASH = re.compile(r"/$")


def trimSlash(source: str) -> str:
    """Remove one trailing slash from ``source`` (only the last)."""
    return _TRAILING_SLASH.sub("", source)


def sanitize(source: str) -> str:
    """Ensure ``source`` starts with ``/`` and has no trailing ``/``.

    Mirrors:

        if (!source.startsWith('/')) source = '/' + source
        return trimSlash(source)
    """
    if not source.startswith("/"):
        source = "/" + source
    return trimSlash(source)
