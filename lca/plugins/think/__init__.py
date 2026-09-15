"""think plugin surface — providers only.

Graph nodes (`think.shortcut`, `think.route`, `think.gate`, `think.reason.*`,
`think.history.assemble`, `think.llm.dispatch`, `think.decision.parse`) live
under :mod:`lca.nodes.think.*` since the unified nodes directory layout
(note 2026-09-15). This package retains only providers (pipeline / role /
reasoner / composition).
"""

from __future__ import annotations

__all__: list[str] = []
