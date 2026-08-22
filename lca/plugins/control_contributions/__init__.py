"""Control contribution executors for ADR-0074.

Each control slot has its own executor module that implements the policy logic
previously in DefaultControlPolicyEngine. These executors return PhaseResult
with ControlVerdict payloads.
"""

from lca.plugins.control_contributions.act_authorize import ActAuthorizeExecutor
from lca.plugins.control_contributions.act_budget import ActBudgetExecutor
from lca.plugins.control_contributions.act_constrain import ActConstrainExecutor
from lca.plugins.control_contributions.act_execute import ActExecuteExecutor
from lca.plugins.control_contributions.act_safe_boundary import ActSafeBoundaryExecutor
from lca.plugins.control_contributions.observe_checkpoint import ObserveCheckpointExecutor
from lca.plugins.control_contributions.perceive_context import PerceiveContextExecutor
from lca.plugins.control_contributions.remember_admit import RememberAdmitExecutor
from lca.plugins.control_contributions.stop_decide import StopDecideExecutor
from lca.plugins.control_contributions.think_guard import ThinkGuardExecutor

__all__ = [
    "ActAuthorizeExecutor",
    "ActBudgetExecutor",
    "ActConstrainExecutor",
    "ActExecuteExecutor",
    "ActSafeBoundaryExecutor",
    "ObserveCheckpointExecutor",
    "PerceiveContextExecutor",
    "RememberAdmitExecutor",
    "StopDecideExecutor",
    "ThinkGuardExecutor",
]
