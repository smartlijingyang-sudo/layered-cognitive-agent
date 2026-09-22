from lca.contracts.models.vocal.models import VocalMode
from lca.contracts.protocols.vocal.protocol import VocalStrategy
from lca.infrastructure.vocal.strategy import DirectVoiceStrategy, GatedVoiceStrategy


class VocalStrategyFactory:
    """声带策略工厂：根据 Assistant 配置或 Run 参数解析当前声带分发策略。"""

    def __init__(self) -> None:
        self._direct = DirectVoiceStrategy()
        self._gated = GatedVoiceStrategy()

    def resolve_strategy(
        self, vocal_mode: str | VocalMode | None = None
    ) -> VocalStrategy:
        if vocal_mode is None:
            return self._direct

        normalized = str(vocal_mode).lower().strip()
        if normalized == VocalMode.GATED.value:
            return self._gated

        return self._direct
