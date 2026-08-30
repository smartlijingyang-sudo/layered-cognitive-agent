"""Service registry — discovery and lookup.

Services register themselves, commands discover them by name.
Simple dict-based registry, no magic.
"""

from __future__ import annotations

from lca.infrastructure.ops.service import Service, ServiceStatus


class ServiceRegistry:
    """Registry of all managed services.

    Design: explicit registration, no auto-discovery magic.
    Factory function creates registry from config.
    """

    def __init__(self) -> None:
        self._services: dict[str, Service] = {}

    def register(self, service: Service) -> None:
        """Register a service."""
        self._services[service.name] = service

    def get(self, name: str) -> Service:
        """Get a service by name. Raises KeyError if not found."""
        return self._services[name]

    def get_optional(self, name: str) -> Service | None:
        """Get a service by name, or None if not found."""
        return self._services.get(name)

    def all(self) -> list[Service]:
        """Get all registered services."""
        return list(self._services.values())

    def names(self) -> list[str]:
        """Get all service names."""
        return list(self._services.keys())

    def unhealthy(self) -> list[Service]:
        """Get services that are not RUNNING."""
        return [
            svc for svc in self._services.values() if svc.state().status != ServiceStatus.RUNNING
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._services

    def __len__(self) -> int:
        return len(self._services)
