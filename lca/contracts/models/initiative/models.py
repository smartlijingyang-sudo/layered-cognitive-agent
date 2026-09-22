from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class InitiativeSignal(StrEnum):
    """主动提议触发信号。"""

    REPEATED_MANUAL = "repeated_manual"
    OBVIOUS_NEXT_STEP = "obvious_next_step"
    MISSING_CONNECTOR = "missing_connector"


class InitiativeOffer(BaseModel):
    """纯函数提议器生成的单条建议载荷。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: InitiativeSignal
    nudge_message: str
    proposed_routine: str | None = None
