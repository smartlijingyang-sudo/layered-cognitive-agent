# -*- coding: utf-8 -*-
"""主动消息领域契约（Proactive Messaging）。

三层架构：
- 触发层：infrastructure/proactive/scheduler（runtime 调度，模型不轮询）；
- 裁决层：cognition/proactive/worthiness（WorthinessGate 纯函数）；
- 投递层：infrastructure/proactive/deliverer（session append，与前端读同一份）。
"""

from lca.contracts.models.proactive.message import (
    DeliveryTarget,
    DeliveryTargetKind,
    ProactiveMessage,
    ProactiveSource,
)
from lca.contracts.models.proactive.schedule import ProactiveJob, TickReport
from lca.contracts.models.proactive.worthiness import (
    ProactiveRequest,
    VerdictKind,
    WorthinessVerdict,
)

__all__ = [
    "DeliveryTarget",
    "DeliveryTargetKind",
    "ProactiveJob",
    "ProactiveMessage",
    "ProactiveRequest",
    "ProactiveSource",
    "TickReport",
    "VerdictKind",
    "WorthinessVerdict",
]
