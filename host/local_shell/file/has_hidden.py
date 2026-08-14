"""Port of packages/local-file-shell/src/file/hasHiddenSegment.ts."""

from __future__ import annotations

import re

HIDDEN_SEGMENT_RE = re.compile(r"(?:^|/)\.[^./]")


def has_hidden_segment(pattern: str | None) -> bool:
    return bool(pattern and HIDDEN_SEGMENT_RE.search(pattern))
