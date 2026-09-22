from lca.contracts.protocols.vocal.protocol import VocalGateProtocol
from lca.infrastructure.vocal.exceptions import UndeliveredTurnError
from lca.infrastructure.vocal.gate import GatedVocalGate


class VocalSettleGuard:
    """声带轮次结算核验硬闸。

    核验规则：
    1. Direct 模式或非 GatedVocalGate 放行；
    2. 若 wake_context.is_silence_allowed == True，允许 0 交付收敛（合规沉默，INV-VOCAL-06）；
    3. 若 is_silence_allowed == False，且未向用户交付任何结果（delivered_count == 0），
       必定阻断收敛并抛出 UndeliveredTurnError（INV-VOCAL-04）。
    """

    def __init__(self, gate: VocalGateProtocol) -> None:
        self._gate = gate

    def validate_turn_settle(self) -> bool:
        if not isinstance(self._gate, GatedVocalGate):
            return True

        # INV-VOCAL-06: 依据 WakeContext 精准判定是否允许合法沉默
        if self._gate.wake_context.is_silence_allowed:
            return True

        # INV-VOCAL-04: 不允许沉默的唤醒源（用户输入/首次启动/入站等），必须有交付
        if self._gate.delivered_count == 0:
            raise UndeliveredTurnError(
                f"轮次收敛失败：唤醒源为 '{self._gate.wake_context.source}'，"
                f"该场景要求必须交付结果，但本轮未通过 send_message 向用户交付任何实质性结果（Ack≠Delivery 违背）。"
            )
        return True
