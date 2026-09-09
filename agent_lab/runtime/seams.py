"""Seams — typed contract between the runner and graph workers.

``Seams`` is the single injection point the runner hands every Worker.
Workers MUST NOT import framework modules (Body, SafeExecutor, Transport,
Session, …) inside ``execute()``; they only call methods on the seams
attribute. The runner is the sole assembler of seam values, so workers
stay minimal and side-effect free at the seam boundary.

Attributes:
    body:  ``SimpleBody`` instance — composition lives in
           ``lca.plugins.lab.act.body_provider`` and is wired here.
    plan_ref: stable identifier for the act-phase plan scope
              (see ``lca.plugins.lab.session.provider.plugin.PLAN_REF``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _SimpleBodyProtocol(Protocol):
    """Surface the worker is allowed to see on the body handle.

    Workers MUST use this Protocol only; importing ``SimpleBody`` in a
    Worker module is a layering violation (L4 application composition
    pulls a layer-1 cognition type into a leaf plugin).
    """

    def act(self, *, intent: dict, plan_ref: str) -> dict:
        ...


@dataclass(frozen=True, slots=True)
class Seams:
    """Typed handle the runner hands every Worker.execute call.

    All attributes are read-only. Workers treat the handle as opaque and
    only call the methods their assigned semantic contract declares.
    """

    body: _SimpleBodyProtocol
    plan_ref: str


__all__ = ["Seams"]