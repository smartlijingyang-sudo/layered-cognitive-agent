from lca.contracts.models.vocal.models import VocalMode
from lca.contracts.models.vocal.wake import WakeContext, WakeSource
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol, VocalStrategy
from lca.infrastructure.vocal.gate import DirectVocalGate, GatedVocalGate


class DirectVoiceStrategy(VocalStrategy):
    """经典直连声带策略。"""

    @property
    def mode(self) -> VocalMode:
        return VocalMode.DIRECT

    def create_gate(
        self,
        operation_id: str,
        wake_source: str | WakeSource = "user_input",
        wake_context: WakeContext | None = None,
    ) -> VocalGateProtocol:
        return DirectVocalGate(operation_id)


class GatedVoiceStrategy(VocalStrategy):
    """门控硬闸声带策略。"""

    @property
    def mode(self) -> VocalMode:
        return VocalMode.GATED

    def create_gate(
        self,
        operation_id: str,
        wake_source: str | WakeSource = "user_input",
        wake_context: WakeContext | None = None,
    ) -> VocalGateProtocol:
        return GatedVocalGate(operation_id, wake_source=wake_source, wake_context=wake_context)
