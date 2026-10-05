"""Shared private helpers for the observation CLI command modules.

Internal seam of this package only: consumed by the sibling command modules
(run_explain / run_replay). Nothing re-exports this module.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.contracts.observability.observation import PlanBlueprint

_LOG = logging.getLogger(__name__)

__all__ = ["_find_blueprint"]


def _find_blueprint(facts: list[dict[str, Any]]) -> PlanBlueprint | None:
    for f in facts:
        if (f.get("execution_point") or "") == "observation.plan_blueprint":
            try:
                return PlanBlueprint.model_validate(f["payload"])
            except Exception as exc:
                _LOG.debug("malformed fact: %s", exc)
                continue
    return None
