import pytest
from pydantic import ValidationError

from lca.contracts.models.vocal.wake import WakeContext, WakeSource


def test_wake_source_enum_values():
    assert WakeSource.USER_INPUT == "user_input"
    assert WakeSource.FIRST_RUN == "first_run"
    assert WakeSource.INBOUND == "inbound"
    assert WakeSource.ROUTINE == "routine"
    assert WakeSource.PEER_AGENT == "peer_agent"
    assert WakeSource.REVIVAL == "revival"


def test_wake_context_frozen():
    ctx = WakeContext(
        source=WakeSource.USER_INPUT,
        is_silence_allowed=False,
        requires_reply_first=True,
    )
    assert ctx.source == WakeSource.USER_INPUT
    with pytest.raises(ValidationError):
        ctx.is_silence_allowed = True  # type: ignore
