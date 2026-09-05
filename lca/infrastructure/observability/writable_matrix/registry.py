"""Writable Face Registry —— 五面矩阵的 profile 装配入口（ADR-0167 D11）。

每面独立 ``@plugin`` 注册，profile / bundle 通过 ``provide(face, instance)``
显式声明装配。Registry 只负责按字符串键解引用 + 不变量校验（I-PLUG2）。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.writable_matrix import (
    Coalescer,
    EventEmitter,
    EventStorage,
    ReplayCursor,
    Serializer,
    StepDriver,
)

_FACE_PROTOCOL: dict[str, type[Any]] = {
    "emitter": EventEmitter,
    "driver": StepDriver,
    "coalescer": Coalescer,
    "serializer": Serializer,
    "storage": EventStorage,
    "replay_cursor": ReplayCursor,
}


class WritableFaceRegistry:
    """Profile 装配期间填充；运行期由 ``StepCoordinator`` 解引用。

    设计要点：

    - 每面只允许一个实例；替换 = 重新注册（profile patch）。
    - ``require`` 在缺失时抛 ``MissingWritableFace``，方便上层 fail-fast。
    - 注册时做 ``isinstance`` 校验 → 不变量 I-PLUG2（Protocol 形态）。
    """

    def __init__(self) -> None:
        self._faces: dict[str, Any] = {}

    def register(self, face: str, instance: Any) -> None:
        if face not in _FACE_PROTOCOL:
            raise ValueError(f"unknown writable face: {face!r}")
        proto = _FACE_PROTOCOL[face]
        if not isinstance(instance, proto):
            raise TypeError(
                f"face {face!r} must satisfy {proto.__name__}, got {type(instance).__name__}"
            )
        self._faces[face] = instance

    def require(self, face: str) -> Any:
        try:
            return self._faces[face]
        except KeyError as exc:
            raise MissingWritableFaceError(face) from exc

    def has(self, face: str) -> bool:
        return face in self._faces

    def faces(self) -> tuple[str, ...]:
        return tuple(self._faces)


class MissingWritableFaceError(LookupError):
    def __init__(self, face: str) -> None:
        super().__init__(f"missing writable face: {face!r}")
        self.face = face
