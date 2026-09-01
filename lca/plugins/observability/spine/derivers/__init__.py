"""Spine deriver plugins — see docs/superpowers/specs/2026-09-01-spine-execution-points-design.md §7.5.4.

Each deriver in this package implements the ``Deriver`` Protocol from
``lca.infrastructure.observability.spine.derivers.base`` and is wrapped
with the project ``@plugin`` decorator so it can be discovered via the
Profile boot DAG. Per I15 / I16 invariant-violation detectors
(``AnomalyDetector``) ship here alongside step-tree / narrative /
graph / live-tail seam plugins.
"""

from __future__ import annotations

__all__: list[str] = []
