from dataclasses import dataclass
from typing import Any

from lca.application.vocal.factory import VocalStrategyFactory
from lca.contracts.models.vocal.models import VocalMode
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard


@dataclass
class RuntimeVocalContext:
    """运行时声带执行上下文绑定。"""

    mode: VocalMode
    gate: VocalGateProtocol
    settle_guard: VocalSettleGuard | None = None


def resolve_runtime_vocal(
    vocal_mode: str | VocalMode | None,
    operation_id: str,
    wake_source: str = "user_input",
    wake_context: Any = None,
) -> RuntimeVocalContext:
    """解析并实例化当前 Run 作用域绑定的声带门控与结算守卫。

    契约保证：
    1. 若未显式指定 vocal_mode 或为 "direct"，走经典直通模式，settle_guard 为 None，零性能开销；
    2. 若显式声明为 "gated"，创建 GatedVocalGate 并装配 VocalSettleGuard。
    """
    factory = VocalStrategyFactory()
    strategy = factory.resolve_strategy(vocal_mode)
    gate = strategy.create_gate(
        operation_id=operation_id,
        wake_source=wake_source,
        wake_context=wake_context,
    )
    guard = VocalSettleGuard(gate) if strategy.mode == VocalMode.GATED else None
    return RuntimeVocalContext(mode=strategy.mode, gate=gate, settle_guard=guard)
