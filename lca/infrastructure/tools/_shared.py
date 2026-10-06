"""infrastructure.tools 下各 tool 家族共享小 helper。"""

from __future__ import annotations

import time

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation

__all__ = ["fail_observation"]


def fail_observation(start: float, message: str) -> Observation:
    """构造参数校验失败的 Observation（success=False + FAILURE_KIND_VALIDATION）。

    曾为 8 个 tool 类各自的 ``_fail`` 方法（字面相同），收敛到此一处；
    行为完全一致。
    """
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error=message,
        latency_ms=int((time.monotonic() - start) * 1000),
        extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
    )
