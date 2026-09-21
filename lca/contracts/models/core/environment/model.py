"""Execution-environment domain model — SSOT for model-visible environment facts.

The reasoner needs one authoritative view of "where it can run": the current
cloud sandbox, a paired companion machine, a future SSH host, and any other
execution plane. :class:`ExecutionEnvironment` is the immutable value object
that carries those facts into both the system-role prompt pipeline and the
``listEnvironments`` tool. It is a *projection* derived from ``PlaneRef`` and
device registries, never a second source of truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from lca.contracts.models.core.state.plane import PlaneRef


class EnvironmentKind(StrEnum):
    """Closed set of environment kinds. Extend with a new member per plane.

    Keeps every member of ``PlaneKind`` plus forward-only kinds (``SSH``)
    that device catalogs may report before a plane exists for them.
    """

    SANDBOX = "sandbox"
    MACHINE = "machine"
    SSH = "ssh"
    POOL_WORKER = "pool_worker"  # ADR-0246 M1


@dataclass(frozen=True)
class ExecutionEnvironment:
    """One execution environment the agent may operate on."""

    kind: EnvironmentKind
    id: str
    label: str
    platform: str
    online: bool
    is_current: bool = False
    root: str = ""
    outputs_dir: str = ""
    home: str = ""
    workspace: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.metadata)
        result.update(
            {
                "kind": self.kind.value,
                "id": self.id,
                "label": self.label,
                "platform": self.platform,
                "online": self.online,
                "is_current": self.is_current,
                "root": self.root,
                "outputs_dir": self.outputs_dir,
                "home": self.home,
                "workspace": self.workspace,
                "capabilities": list(self.capabilities),
            }
        )
        return result


def environment_from_plane(
    plane: PlaneRef,
    *,
    is_current: bool = False,
    online: bool = True,
    extra: Mapping[str, Any] | None = None,
) -> ExecutionEnvironment:
    """Project an :class:`ExecutionEnvironment` from a runtime ``PlaneRef``.

    ``online`` defaults to ``True`` because a resolved plane is reachable.
    ``extra`` carries kind-specific metadata (device payload, SSH host, ...).
    """
    return ExecutionEnvironment(
        kind=EnvironmentKind(plane.kind.value),
        id=plane.id,
        label=plane.label,
        platform=plane.platform,
        online=online,
        is_current=is_current,
        root=plane.root,
        outputs_dir=plane.outputs_dir,
        home=plane.home,
        capabilities=tuple(plane.capability_summary),
        metadata=dict(extra or {}),
    )


__all__ = ["EnvironmentKind", "ExecutionEnvironment", "environment_from_plane"]
