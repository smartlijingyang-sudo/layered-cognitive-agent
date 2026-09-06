"""Control contribution executors for ADR-0074.

Each control slot has its own executor module that implements the policy logic
previously in DefaultControlPolicyEngine. These executors return PhaseResult
with ControlVerdict payloads.
"""

from lca.plugins.loop.control.act_authorize.plugin import ActAuthorizeExecutor
from lca.plugins.loop.control.act_budget.plugin import ActBudgetExecutor
from lca.plugins.loop.control.act_constrain.plugin import ActConstrainExecutor
from lca.plugins.loop.control.act_execute.plugin import ActExecuteExecutor
from lca.plugins.loop.control.act_safe_boundary.plugin import ActSafeBoundaryExecutor
from lca.plugins.loop.control.observe_checkpoint.plugin import ObserveCheckpointExecutor
from lca.plugins.loop.control.observe_wildcard.plugin import ObserveWildcardExecutor
from lca.plugins.loop.control.perceive_context.plugin import PerceiveContextExecutor
from lca.plugins.loop.control.remember_admit.plugin import RememberAdmitExecutor
from lca.plugins.loop.control.stop_decide.plugin import StopDecideExecutor
from lca.plugins.loop.control.stop_focus.plugin import FocusStopExecutor
from lca.plugins.loop.control.think_guard.plugin import (
    ThinkGuardEnforceExecutor,
    ThinkGuardExecutor,
)

__all__ = [
    "ActAuthorizeExecutor",
    "ActBudgetExecutor",
    "ActConstrainExecutor",
    "ActExecuteExecutor",
    "ActSafeBoundaryExecutor",
    "FocusStopExecutor",
    "ObserveCheckpointExecutor",
    "ObserveWildcardExecutor",
    "PerceiveContextExecutor",
    "RememberAdmitExecutor",
    "StopDecideExecutor",
    "ThinkGuardEnforceExecutor",
    "ThinkGuardExecutor",
]
