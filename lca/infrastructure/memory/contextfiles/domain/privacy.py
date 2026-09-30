"""Personal-disclosure filter for branch retrieval.

Main-session search may return every active record. A side-chat search must
not hand private main-session text to the model. The check is a content
pattern, not a second store.
"""

from __future__ import annotations

import re

from lca.infrastructure.memory.contextfiles.domain.curated import contains_secret

_PRIVATE = re.compile(r"作息|病史|住址|家庭地址|身份证|手机号|电话号|病历")


def is_private_personal(content: str) -> bool:
    """Return whether ``content`` is private personal material."""

    text = content.strip()
    if not text:
        return False
    return contains_secret(text) or _PRIVATE.search(text) is not None


__all__ = ["is_private_personal"]
