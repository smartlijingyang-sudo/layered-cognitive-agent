"""Framework package: unified graph kernel and its supporting modules.

The legacy ``lca.framework.declarative`` and ``lca.framework.subgraph``
subpackages were deleted in the act-subgraph seam cutover (note
2026-09-11). The production interpreter is now
:class:`lca.framework.graph.adapter.PlanInterpreterAdapter` and the
single visit state machine lives at :mod:`lca.framework.graph`.

Business-domain plugins (think / reflect / runtime_provider …) live
under :mod:`lca.plugins` and must remain independent from anything
inside this package.
"""

from __future__ import annotations

__all__: list[str] = []
