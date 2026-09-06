"""Public exports for ``execution`` (auto-fixed)."""

from lca.infrastructure.runtime_plane.execution.target import (
    ExecutionPlan,
    ExecutionTarget,
    parse_execution_target,
    resolve_execution_target,
)

__all__ = ['ExecutionTarget', 'ExecutionPlan', 'parse_execution_target', 'resolve_execution_target']
