"""Execution-environment domain model (SSOT for model-visible environment facts)."""

from lca.contracts.models.core.environment.model import (
    EnvironmentKind,
    ExecutionEnvironment,
    environment_from_plane,
)

__all__ = ["EnvironmentKind", "ExecutionEnvironment", "environment_from_plane"]
