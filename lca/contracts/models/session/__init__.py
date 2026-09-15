"""Session-scoped contracts used by the run session writer Protocol.

Each module is a minimal TypedDict / alias re-export so the
``RunSessionWriterProtocol`` can reference its parameter and return shapes
without depending on the kernel layer.
"""

from lca.contracts.models.session.call_id import CallId
from lca.contracts.models.session.epoch_header import EpochHeader
from lca.contracts.models.session.event_ref import EventRef
from lca.contracts.models.session.message import Message, ToolCallRef
from lca.contracts.models.session.token_usage import TokenUsage
from lca.contracts.models.session.tool_call import ToolCall
from lca.contracts.models.session.tool_error import ToolError

__all__ = [
    "CallId",
    "EpochHeader",
    "EventRef",
    "Message",
    "TokenUsage",
    "ToolCall",
    "ToolCallRef",
    "ToolError",
]
