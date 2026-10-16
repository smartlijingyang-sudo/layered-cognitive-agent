"""One spelling map for wire tool names.

The computer registry stores camelCase. Prompts and models also emit
snake_case for the same tool. The defer gate and the approval check both
have to apply this map. Otherwise a loaded tool is refused under the other
spelling, or an unloaded shell name pauses for approval.
"""

from __future__ import annotations

import re

_CAMEL_BOUNDARY_RE = re.compile(r"(?<!^)(?=[A-Z])")


def canonical_tool_name(name: str) -> str:
    """Return the other spelling of a wire tool name."""
    if not name:
        return name
    if "_" in name:
        parts = name.split("_")
        return parts[0] + "".join(part.capitalize() for part in parts[1:] if part)
    if any(char.isupper() for char in name[1:]):
        return _CAMEL_BOUNDARY_RE.sub("_", name).lower()
    return name
