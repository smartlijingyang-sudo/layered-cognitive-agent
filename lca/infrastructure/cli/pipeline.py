"""Pipeline execution — commands as step sequences.

A command is a named sequence of steps. Each step is a callable that
receives a PipelineContext and performs one atomic operation.

Design: steps are registered functions, commands are YAML-driven sequences.
This allows composition, reordering, and conditional execution.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeAlias

from lca.infrastructure.cli.config import OpsConfig
from lca.infrastructure.cli.console import Console
from lca.infrastructure.cli.registry import ServiceRegistry
from lca.infrastructure.cli.state import StateStore


@dataclass
class PipelineContext:
    """Context passed to every step.

    Provides access to config, services, state, and console.
    Steps should not hold state themselves — everything goes through context.
    """

    config: OpsConfig
    registry: ServiceRegistry
    state: StateStore
    console: Console
    failed: bool = False
    log: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        """Mark pipeline as failed."""
        self.failed = True
        self.console.error(reason)
        self.log.append(f"FAIL: {reason}")

    def record(self, message: str) -> None:
        """Record a step execution."""
        self.log.append(message)
        self.console.step(message)


# Step is just a function: receive context, perform action, return nothing.
# Side effects are tracked via context.console and context.state.
Step: TypeAlias = Callable[[PipelineContext], None]


class Pipeline:
    """Executes a sequence of steps.

    Design: fail-fast by default. Steps can check context.failed to skip work.
    """

    def __init__(self, name: str, steps: list[tuple[str, Step]]) -> None:
        self.name = name
        self.steps = steps  # list of (step_name, step_fn)

    def execute(self, context: PipelineContext) -> bool:
        """Execute all steps in order.

        Returns True if all steps succeeded, False if any failed.
        """
        context.console.info(f"Pipeline: {self.name}")

        for step_name, step_fn in self.steps:
            if context.failed:
                context.console.warning(f"Skipping {step_name} (pipeline failed)")
                break

            try:
                context.record(step_name)
                step_fn(context)
            except Exception as e:
                context.fail(f"{step_name}: {e}")
                break

        return not context.failed


# ── Step Registry ─────────────────────────────────────────────────────

# Global step registry. Steps register themselves via @register_step.
_STEP_REGISTRY: dict[str, Step] = {}


def register_step(name: str) -> Callable[[Step], Step]:
    """Decorator to register a step function.

    Usage:
        @register_step("lobehub.start")
        def start_lobehub(context: PipelineContext) -> None:
            ...
    """

    def decorator(step: Step) -> Step:
        _STEP_REGISTRY[name] = step
        return step

    return decorator


def get_step(name: str) -> Step:
    """Get a registered step by name. Raises KeyError if not found."""
    return _STEP_REGISTRY[name]


def build_pipeline(name: str, step_names: list[str]) -> Pipeline:
    """Build a pipeline from a list of step names.

    Steps are looked up in the global registry.
    """
    steps = [(step_name, get_step(step_name)) for step_name in step_names]
    return Pipeline(name, steps)
