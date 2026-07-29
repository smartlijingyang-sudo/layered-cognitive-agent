"""团队委派进度台账 —— 默认实现与 hooks。"""

from lca.layer1_cognitive.team_progress.delegation_ledger import DelegationLedger
from lca.layer1_cognitive.team_progress.hooks import (
    ledger_tracking_hook,
    progress_injection_hook,
)

__all__ = [
    "DelegationLedger",
    "ledger_tracking_hook",
    "progress_injection_hook",
]
