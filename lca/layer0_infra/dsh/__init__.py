"""DeepSeek Harness compare driver.

A Run *driver*, not a third execution plane. LCA sets SDK launch (cwd, cordis,
env paths); DSH owns agent loop, skills, and workspaceContext. Journal
projection is the only LobeHub-facing adapter.
"""

from lca.layer0_infra.dsh.driver import DshTurnDriver, DshTurnSpec
from lca.layer0_infra.dsh.models import DshNotification, DshTurnResult
from lca.layer0_infra.dsh.prompt import compose_dsh_prompt
from lca.layer0_infra.dsh.routing import is_dsh_driver
from lca.layer0_infra.dsh.run import run_dsh_machine_turn
from lca.layer0_infra.dsh.settings import DshSettings

__all__ = [
    "DshNotification",
    "DshSettings",
    "DshTurnDriver",
    "DshTurnResult",
    "DshTurnSpec",
    "compose_dsh_prompt",
    "is_dsh_driver",
    "run_dsh_machine_turn",
]
