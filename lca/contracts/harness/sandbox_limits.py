"""Declarative resource limits for sandbox execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxResourceLimits:
    timeout_s: int = 60
    max_output_bytes: int = 8_000_000
    max_files: int = 20
    max_file_bytes: int = 20 * 1024 * 1024
    network_enabled: bool = False

    def __post_init__(self) -> None:
        if self.timeout_s <= 0:
            raise ValueError("sandbox timeout must be positive")
        if self.max_output_bytes < 0 or self.max_files < 0 or self.max_file_bytes < 0:
            raise ValueError("sandbox resource limits must be non-negative")

    def allows_file(self, size_bytes: int, current_count: int) -> bool:
        return (
            size_bytes >= 0
            and current_count >= 0
            and current_count < self.max_files
            and size_bytes <= self.max_file_bytes
        )


__all__ = ["SandboxResourceLimits"]
