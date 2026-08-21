"""Content-addressable store —— 内容寻址存储契约(ADR-0065 §一)。

``EvidenceStore`` 把"如何放"和"放哪里"分到两层:
- ContentAddressableStore 提供``put(bytes)→digest``与``get(digest)→bytes``的纯 CAS。
- EvidenceStore 在其上加 classification / retention / policy。

本模块只定义 CAS 契约与一个纯内存实现;fs / s3 backend 由具体 provider 提供。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class ContentAddressableStore(Protocol):
    """纯 CAS:内容寻址、按摘要读、不可变。"""

    def put(self, payload: bytes, *, media_type: str = "application/octet-stream") -> str:
        """存一份 payload;返回 sha256 hex digest。"""

    def get(self, digest: str) -> bytes:
        """按 digest 取回;缺失抛 KeyError。"""

    def contains(self, digest: str) -> bool:
        """纯存在性检查,不读内容。"""

    def sweep_orphan(self, live_digests: set[str]) -> int:
        """清掉不在 live_digests 集合的 digest;返回清掉数量;幂等。"""


@dataclass(frozen=True)
class InMemoryContentAddressableStore:
    """纯内存 CAS —— 测试 / 默认 fallback。

    bytes-as-key dict,put 自动覆盖(同 digest 必然同 bytes)。
    """

    _items: dict[str, bytes] = field(default_factory=dict)

    def put(self, payload: bytes, *, media_type: str = "application/octet-stream") -> str:
        digest = hashlib.sha256(payload).hexdigest()
        self._items[digest] = payload
        return digest

    def get(self, digest: str) -> bytes:
        try:
            return self._items[digest]
        except KeyError as exc:
            raise KeyError(f"digest not found: {digest}") from exc

    def contains(self, digest: str) -> bool:
        return digest in self._items

    def sweep_orphan(self, live_digests: set[str]) -> int:
        stale = [d for d in self._items if d not in live_digests]
        for d in stale:
            del self._items[d]
        return len(stale)


__all__ = [
    "ContentAddressableStore",
    "InMemoryContentAddressableStore",
]
