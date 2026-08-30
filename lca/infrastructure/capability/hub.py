"""CapabilityHub — 进程内 ctx：每个键挂一个 Definition 服务。"""

from __future__ import annotations

from typing import Any

from lca.contracts.mechanisms.capability import MissingCapabilityError


class CapabilityHub:
    """进程内 ctx 的 Python 实现。mount 一次；之后只通过键取 Definition。"""

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}

    def mount(self, key: str, service: Any) -> None:
        if not key:
            raise ValueError("capability key is empty")
        if key in self._services:
            raise RuntimeError(f"capability {key!r} already mounted")
        self._services[key] = service

    def require(self, key: str) -> Any:
        service = self._services.get(key)
        if service is None:
            raise MissingCapabilityError(key)
        return service

    def get(self, key: str) -> Any | None:
        return self._services.get(key)

    def keys(self) -> list[str]:
        return list(self._services)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.require(name)
        except MissingCapabilityError as exc:
            raise AttributeError(name) from exc
